"""In-memory per-user conversation state for the local Telegram demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ConversationStatus(str, Enum):
    IDLE = "IDLE"
    AWAITING_SLOT_CONFIRMATION = "AWAITING_SLOT_CONFIRMATION"
    AWAITING_EMAIL = "AWAITING_EMAIL"
    BOOKED = "BOOKED"


@dataclass(frozen=True)
class ConversationState:
    """One Telegram user's current deterministic booking context."""

    user_id: int
    status: ConversationStatus = ConversationStatus.IDLE
    requested_start: datetime | None = None
    proposed_start: datetime | None = None
    selected_start: datetime | None = None
    patient_email: str | None = None
    calendar_event_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "requested_start",
            "proposed_start",
            "selected_start",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError(f"{field_name} must be timezone-aware")

        if (
            self.status == ConversationStatus.AWAITING_SLOT_CONFIRMATION
            and self.proposed_start is None
        ):
            raise ValueError(
                "AWAITING_SLOT_CONFIRMATION requires a proposed slot"
            )
        if (
            self.status == ConversationStatus.AWAITING_EMAIL
            and self.selected_start is None
        ):
            raise ValueError("AWAITING_EMAIL requires a selected slot")
        if self.status == ConversationStatus.BOOKED:
            if self.selected_start is None:
                raise ValueError("BOOKED requires a selected slot")
            if not self.calendar_event_id:
                raise ValueError("BOOKED requires a Calendar event ID")


class InMemoryConversationStore:
    """Store isolated conversation state by Telegram user ID.

    This local-demo store is intentionally non-persistent. Production or
    multi-instance deployments would require shared persistent storage.
    """

    def __init__(self) -> None:
        self._states: dict[int, ConversationState] = {}

    def get(self, user_id: int) -> ConversationState:
        return self._states.get(user_id, ConversationState(user_id=user_id))

    def save(self, state: ConversationState) -> None:
        self._states[state.user_id] = state

    def reset(self, user_id: int) -> ConversationState:
        state = ConversationState(user_id=user_id)
        self.save(state)
        return state
