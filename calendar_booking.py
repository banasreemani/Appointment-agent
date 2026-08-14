"""Create BrightCare Clinic appointments in Google Calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from calendar_availability import (
    APPOINTMENT_DURATION,
    CalendarConfig,
    check_calendar_availability,
)


BOOKING_SCOPES = ["https://www.googleapis.com/auth/calendar"]
EVENT_TITLE = "BrightCare Clinic Appointment"
EVENT_DESCRIPTION = "Booked via BrightCare Clinic appointment agent"


@dataclass(frozen=True)
class BookingResult:
    """Structured outcome of one appointment booking attempt."""

    success: bool
    appointment_start: datetime
    appointment_end: datetime
    event_id: str | None = None
    reason: str | None = None


def build_booking_calendar_service(config: CalendarConfig) -> Any:
    """Create a Google Calendar service authorized to insert events."""
    credentials = service_account.Credentials.from_service_account_file(
        config.credential_file,
        scopes=BOOKING_SCOPES,
    )
    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def _failure(appointment_start: datetime, reason: str) -> BookingResult:
    return BookingResult(
        success=False,
        appointment_start=appointment_start,
        appointment_end=appointment_start + APPOINTMENT_DURATION,
        reason=reason,
    )


def book_appointment(
    appointment_start: datetime,
    patient_email: str,
    service: Any,
    calendar_id: str,
    clinic_timezone: ZoneInfo,
    patient_name: str | None = None,
) -> BookingResult:
    """Re-check one exact slot and insert its calendar event if still free.

    FreeBusy and events.insert are separate Google API operations. Re-checking
    immediately before insertion reduces the race window, but it does not make
    the reservation fully atomic.
    """
    patient_email = patient_email.strip()
    if not patient_email:
        return _failure(appointment_start, "Patient email is required.")

    try:
        availability = check_calendar_availability(
            appointment_start,
            service,
            calendar_id,
            clinic_timezone,
        )
    except (ValueError, OSError, RuntimeError, GoogleAuthError, HttpError) as error:
        return _failure(
            appointment_start,
            f"Unable to re-check Google Calendar availability: {error}",
        )

    normalized_start = availability.requested_start
    appointment_end = normalized_start + APPOINTMENT_DURATION

    if not availability.valid_request:
        return BookingResult(
            success=False,
            appointment_start=normalized_start,
            appointment_end=appointment_end,
            reason=availability.reason,
        )

    if not availability.available:
        return BookingResult(
            success=False,
            appointment_start=normalized_start,
            appointment_end=appointment_end,
            reason="The requested slot is no longer available.",
        )

    description_lines = [
        EVENT_DESCRIPTION,
        f"Patient email: {patient_email}",
    ]
    if patient_name and patient_name.strip():
        description_lines.append(f"Patient name: {patient_name.strip()}")

    event_body = {
        "summary": EVENT_TITLE,
        "description": "\n".join(description_lines),
        "start": {
            "dateTime": normalized_start.isoformat(),
            "timeZone": clinic_timezone.key,
        },
        "end": {
            "dateTime": appointment_end.isoformat(),
            "timeZone": clinic_timezone.key,
        },
    }

    try:
        created_event = (
            service.events()
            .insert(
                calendarId=calendar_id,
                body=event_body,
            )
            .execute()
        )
    except (OSError, GoogleAuthError, HttpError) as error:
        return BookingResult(
            success=False,
            appointment_start=normalized_start,
            appointment_end=appointment_end,
            reason=f"Google Calendar event insertion failed: {error}",
        )

    event_id = created_event.get("id")
    if not event_id:
        return BookingResult(
            success=False,
            appointment_start=normalized_start,
            appointment_end=appointment_end,
            reason="Google Calendar did not return an event ID.",
        )

    return BookingResult(
        success=True,
        appointment_start=normalized_start,
        appointment_end=appointment_end,
        event_id=event_id,
    )
