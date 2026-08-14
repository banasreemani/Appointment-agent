"""Deterministic Telegram booking state and availability workflow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
import logging
from typing import Any, Callable
from zoneinfo import ZoneInfo

from calendar_availability import (
    AvailabilityResult,
    check_calendar_availability,
)
from calendar_booking import BookingResult, book_appointment
from conversation_state import (
    ConversationState,
    ConversationStatus,
    InMemoryConversationStore,
)
from email_validation import normalize_email_address
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
INVALID_EMAIL_RESPONSE = (
    "That doesn't look like a valid email address. Please send a valid email "
    "address."
)
BOOKING_FAILURE_RESPONSE = (
    "I couldn't complete the booking just now. Please try again."
)
SLOT_TAKEN_NO_AVAILABILITY_RESPONSE = (
    "That slot is no longer available, and there are no remaining appointments "
    "that day. Please choose another day."
)
SLOT_NO_LONGER_AVAILABLE_REASON = "The requested slot is no longer available."

AvailabilityChecker = Callable[
    [datetime, Any, str, ZoneInfo], AvailabilityResult
]
BookingCreator = Callable[
    [datetime, str, Any, str, ZoneInfo], BookingResult
]
ConfirmationEmailSender = Callable[[str, datetime], None]
EmailValidator = Callable[[str], str | None]


def _format_time(value: time) -> str:
    period = "am" if value.hour < 12 else "pm"
    display_hour = value.hour % 12 or 12
    return f"{display_hour}:{value.minute:02d}{period}"


@dataclass
class TelegramBookingWorkflow:
    """Coordinate validated intents, state, Calendar booking, and email."""

    state_store: InMemoryConversationStore
    calendar_service: Any
    calendar_id: str
    clinic_timezone: ZoneInfo
    availability_checker: AvailabilityChecker = check_calendar_availability
    booking_creator: BookingCreator = book_appointment
    confirmation_email_sender: ConfirmationEmailSender | None = None
    email_validator: EmailValidator = normalize_email_address

    def is_awaiting_email(self, user_id: int) -> bool:
        """Return whether raw text should be treated as an email answer."""
        return (
            self.state_store.get(user_id).status
            == ConversationStatus.AWAITING_EMAIL
        )

    def handle_expected_email(self, user_id: int, message_text: str) -> str:
        """Validate an expected raw email without involving the LLM."""
        state = self.state_store.get(user_id)
        if state.status != ConversationStatus.AWAITING_EMAIL:
            return response_for_intent(IntentResult(intent=Intent.OTHER))

        patient_email = self.email_validator(message_text)
        if patient_email is None:
            return INVALID_EMAIL_RESPONSE

        state_with_email = replace(state, patient_email=patient_email)
        self.state_store.save(state_with_email)
        return self._complete_booking(state_with_email)

    def handle_intent(self, user_id: int, result: IntentResult) -> str:
        """Handle one validated intent using deterministic workflow state."""
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
        validated_email = self.email_validator(state.patient_email or "")
        if validated_email is not None:
            state_with_email = replace(
                new_state,
                patient_email=validated_email,
            )
            self.state_store.save(state_with_email)
            return self._complete_booking(state_with_email)
        if new_state.patient_email is not None:
            self.state_store.save(replace(new_state, patient_email=None))
        return ASK_FOR_EMAIL_RESPONSE

    def _complete_booking(self, state: ConversationState) -> str:
        selected_start = state.selected_start
        if selected_start is None:
            return BOOKING_FAILURE_RESPONSE

        LOGGER.info(
            "Final Calendar availability re-check user_id=%s appointment=%s",
            state.user_id,
            selected_start.isoformat(),
        )
        try:
            availability = self.availability_checker(
                selected_start,
                self.calendar_service,
                self.calendar_id,
                self.clinic_timezone,
            )
        except Exception:
            LOGGER.exception(
                "Final Calendar availability re-check failed user_id=%s",
                state.user_id,
            )
            return BOOKING_FAILURE_RESPONSE

        if not availability.valid_request:
            LOGGER.error(
                "Stored selected slot failed validation user_id=%s reason=%s",
                state.user_id,
                availability.reason,
            )
            return BOOKING_FAILURE_RESPONSE
        if not availability.available:
            return self._handle_concurrency_conflict(state, availability)

        patient_email = state.patient_email
        if patient_email is None:
            return ASK_FOR_EMAIL_RESPONSE

        try:
            booking = self.booking_creator(
                selected_start,
                patient_email,
                self.calendar_service,
                self.calendar_id,
                self.clinic_timezone,
            )
        except Exception:
            LOGGER.exception(
                "Calendar event creation failed user_id=%s",
                state.user_id,
            )
            return BOOKING_FAILURE_RESPONSE

        if not booking.success:
            LOGGER.error(
                "Calendar event creation failed user_id=%s reason=%s",
                state.user_id,
                booking.reason,
            )
            if booking.reason == SLOT_NO_LONGER_AVAILABLE_REASON:
                return self._refresh_after_insert_race(state)
            return BOOKING_FAILURE_RESPONSE

        booked_state = ConversationState(
            user_id=state.user_id,
            status=ConversationStatus.BOOKED,
            requested_start=state.requested_start,
            proposed_start=state.proposed_start,
            selected_start=booking.appointment_start,
            patient_email=patient_email,
            calendar_event_id=booking.event_id,
        )
        self._save_transition(state, booked_state)
        LOGGER.info(
            "Calendar booking committed user_id=%s event_id=%s",
            state.user_id,
            booking.event_id,
        )

        try:
            if self.confirmation_email_sender is None:
                raise RuntimeError("Confirmation email sender is not configured")
            self.confirmation_email_sender(
                patient_email,
                booking.appointment_start,
            )
        except Exception:
            LOGGER.exception(
                "Confirmation email delivery failed user_id=%s",
                state.user_id,
            )
            return self._email_failure_response(booking.appointment_start)

        LOGGER.info("Confirmation email delivered user_id=%s", state.user_id)
        return self._booking_success_response(booking.appointment_start)

    def _refresh_after_insert_race(self, state: ConversationState) -> str:
        selected_start = state.selected_start
        if selected_start is None:
            return BOOKING_FAILURE_RESPONSE
        try:
            availability = self.availability_checker(
                selected_start,
                self.calendar_service,
                self.calendar_id,
                self.clinic_timezone,
            )
        except Exception:
            LOGGER.exception(
                "Calendar conflict refresh failed user_id=%s",
                state.user_id,
            )
            return BOOKING_FAILURE_RESPONSE
        if availability.available:
            return BOOKING_FAILURE_RESPONSE
        return self._handle_concurrency_conflict(state, availability)

    def _handle_concurrency_conflict(
        self,
        state: ConversationState,
        availability: AvailabilityResult,
    ) -> str:
        LOGGER.info("Selected slot is no longer free user_id=%s", state.user_id)
        if availability.nearest_available_start is None:
            idle_state = ConversationState(user_id=state.user_id)
            self._save_transition(state, idle_state)
            return SLOT_TAKEN_NO_AVAILABILITY_RESPONSE

        new_state = ConversationState(
            user_id=state.user_id,
            status=ConversationStatus.AWAITING_SLOT_CONFIRMATION,
            requested_start=state.selected_start,
            proposed_start=availability.nearest_available_start,
            patient_email=state.patient_email,
        )
        self._save_transition(state, new_state)
        return (
            "That slot was just taken. The nearest available opening is "
            f"{_format_time(availability.nearest_available_start.time())} — "
            "shall I book that instead?"
        )

    @staticmethod
    def _booking_success_response(appointment_start: datetime) -> str:
        weekday = appointment_start.strftime("%A")
        return (
            f"Done — you're booked for {weekday} at "
            f"{_format_time(appointment_start.time())}. A confirmation email "
            "has been sent to your email address. Anything else?"
        )

    @staticmethod
    def _email_failure_response(appointment_start: datetime) -> str:
        weekday = appointment_start.strftime("%A")
        return (
            f"Your appointment is booked for {weekday} at "
            f"{_format_time(appointment_start.time())}, but I couldn't send "
            "the confirmation email. Please contact the clinic if you need "
            "the confirmation resent."
        )

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
