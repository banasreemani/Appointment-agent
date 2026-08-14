"""Deterministic Telegram booking state and availability workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import logging
from typing import Any, Callable
from zoneinfo import ZoneInfo

from calendar_availability import (
    AvailabilityResult,
    check_calendar_availability,
)
from conversation_state import (
    ConversationState,
    ConversationStatus,
    InMemoryConversationStore,
)
from intent_parser import Intent, IntentResult
from telegram_intent_responses import response_for_intent


LOGGER = logging.getLogger(__name__)
ASK_FOR_EMAIL_RESPONSE = (
    "Great. What email address should I use for your booking confirmation?"
)
DECLINE_SLOT_RESPONSE = "No problem. What other date and time would you like?"
NO_AVAILABILITY_RESPONSE = (
    "There are no remaining 30-minute appointments available that day. "
    "Please choose another day."
)
CALENDAR_ERROR_RESPONSE = (
    "Sorry, I couldn't check Google Calendar right now. Please try again."
)

AvailabilityChecker = Callable[
    [datetime, Any, str, ZoneInfo], AvailabilityResult
]


def _format_time(value: time) -> str:
    period = "am" if value.hour < 12 else "pm"
    display_hour = value.hour % 12 or 12
    return f"{display_hour}:{value.minute:02d}{period}"


@dataclass
class TelegramBookingWorkflow:
    """Coordinate validated intents, user state, and Calendar FreeBusy."""

    state_store: InMemoryConversationStore
    calendar_service: Any
    calendar_id: str
    clinic_timezone: ZoneInfo
    availability_checker: AvailabilityChecker = check_calendar_availability

    def handle_intent(self, user_id: int, result: IntentResult) -> str:
        """Handle one validated intent without creating Calendar events."""
        state = self.state_store.get(user_id)

        if result.intent == Intent.BOOKING:
            return self._handle_booking(state, result)

        if state.status == ConversationStatus.AWAITING_SLOT_CONFIRMATION:
            if result.intent == Intent.AFFIRM:
                return self._confirm_proposed_slot(state)
            if result.intent == Intent.DECLINE:
                reset_state = ConversationState(user_id=user_id)
                self._save_transition(state, reset_state)
                return DECLINE_SLOT_RESPONSE

        return response_for_intent(result)

    def _handle_booking(
        self,
        previous_state: ConversationState,
        result: IntentResult,
    ) -> str:
        if result.requested_date is None or result.requested_time is None:
            return response_for_intent(result)

        requested_start = datetime.combine(
            result.requested_date,
            result.requested_time,
            tzinfo=self.clinic_timezone,
        )

        try:
            availability = self.availability_checker(
                requested_start,
                self.calendar_service,
                self.calendar_id,
                self.clinic_timezone,
            )
        except Exception:
            LOGGER.exception(
                "Google Calendar availability check failed for user_id=%s",
                previous_state.user_id,
            )
            return CALENDAR_ERROR_RESPONSE

        if not availability.valid_request:
            idle_state = ConversationState(user_id=previous_state.user_id)
            self._save_transition(previous_state, idle_state)
            return availability.reason or "That appointment time is not valid."

        if availability.available:
            proposed_start = availability.requested_start
            new_state = ConversationState(
                user_id=previous_state.user_id,
                status=ConversationStatus.AWAITING_SLOT_CONFIRMATION,
                requested_start=availability.requested_start,
                proposed_start=proposed_start,
                patient_email=result.email,
            )
            self._save_transition(previous_state, new_state)
            weekday = proposed_start.strftime("%A")
            return (
                f"{weekday} at {_format_time(proposed_start.time())} is "
                "available — shall I book that?"
            )

        if availability.nearest_available_start is None:
            idle_state = ConversationState(user_id=previous_state.user_id)
            self._save_transition(previous_state, idle_state)
            return NO_AVAILABILITY_RESPONSE

        proposed_start = availability.nearest_available_start
        new_state = ConversationState(
            user_id=previous_state.user_id,
            status=ConversationStatus.AWAITING_SLOT_CONFIRMATION,
            requested_start=availability.requested_start,
            proposed_start=proposed_start,
            patient_email=result.email,
        )
        self._save_transition(previous_state, new_state)
        weekday = availability.requested_start.strftime("%A")
        return (
            f"{_format_time(availability.requested_start.time())} {weekday} "
            "isn't available. The nearest opening is "
            f"{_format_time(proposed_start.time())} — shall I book that?"
        )

    def _confirm_proposed_slot(self, state: ConversationState) -> str:
        if state.proposed_start is None:
            return response_for_intent(IntentResult(intent=Intent.AFFIRM))

        new_state = ConversationState(
            user_id=state.user_id,
            status=ConversationStatus.AWAITING_EMAIL,
            requested_start=state.requested_start,
            proposed_start=state.proposed_start,
            selected_start=state.proposed_start,
            patient_email=state.patient_email,
        )
        self._save_transition(state, new_state)
        return ASK_FOR_EMAIL_RESPONSE

    def _save_transition(
        self,
        previous_state: ConversationState,
        new_state: ConversationState,
    ) -> None:
        self.state_store.save(new_state)
        if previous_state.status != new_state.status:
            LOGGER.info(
                "user_id=%s %s -> %s",
                new_state.user_id,
                previous_state.status.value,
                new_state.status.value,
            )
