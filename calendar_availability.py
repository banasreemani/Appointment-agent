"""Google Calendar-backed availability rules for BrightCare Clinic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.oauth2 import service_account
from googleapiclient.discovery import build

from environment_config import required_environment_variable


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
BUSINESS_OPEN = time(9, 0)
BUSINESS_CLOSE = time(18, 0)
APPOINTMENT_DURATION = timedelta(minutes=30)

BusyInterval = tuple[datetime, datetime]


@dataclass(frozen=True)
class CalendarConfig:
    """Configuration required to query the clinic calendar."""

    calendar_id: str
    credential_file: Path
    timezone: ZoneInfo


@dataclass(frozen=True)
class AvailabilityResult:
    """Availability and, when needed, the nearest same-day alternative."""

    requested_start: datetime
    valid_request: bool
    available: bool
    nearest_available_start: datetime | None
    reason: str | None = None


def load_calendar_config() -> CalendarConfig:
    """Load calendar settings from the project environment."""
    calendar_id = required_environment_variable("GOOGLE_CALENDAR_ID")
    credential_file = Path(
        required_environment_variable("GOOGLE_SERVICE_ACCOUNT_FILE")
    ).expanduser()
    timezone_name = required_environment_variable("CLINIC_TIMEZONE")

    if not credential_file.is_file():
        raise ValueError(f"Service-account file not found: {credential_file}")

    try:
        clinic_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown clinic timezone: {timezone_name}") from error

    return CalendarConfig(calendar_id, credential_file, clinic_timezone)


def build_calendar_service(config: CalendarConfig) -> Any:
    """Create a read-only Google Calendar API service."""
    credentials = service_account.Credentials.from_service_account_file(
        config.credential_file,
        scopes=SCOPES,
    )
    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def _clinic_datetime(day: date, value: time, clinic_timezone: ZoneInfo) -> datetime:
    return datetime.combine(day, value, tzinfo=clinic_timezone)


def _normalize_request(
    requested_start: datetime, clinic_timezone: ZoneInfo
) -> datetime:
    if requested_start.tzinfo is None or requested_start.utcoffset() is None:
        raise ValueError("Requested start must be timezone-aware")
    return requested_start.astimezone(clinic_timezone)


def _invalid_reason(requested_start: datetime) -> str | None:
    if requested_start.weekday() >= 5:
        return "The clinic is closed on weekends."

    opening = _clinic_datetime(
        requested_start.date(), BUSINESS_OPEN, requested_start.tzinfo
    )
    closing = _clinic_datetime(
        requested_start.date(), BUSINESS_CLOSE, requested_start.tzinfo
    )
    requested_end = requested_start + APPOINTMENT_DURATION

    if requested_start < opening:
        return "The requested slot starts before the clinic opens at 09:00."
    if requested_start >= closing:
        return "The requested slot must start before the clinic closes at 18:00."
    if requested_end > closing:
        return "The requested appointment would end after 18:00."
    if (
        requested_start.minute not in (0, 30)
        or requested_start.second != 0
        or requested_start.microsecond != 0
    ):
        return "Appointment start times must be on a 30-minute boundary."
    return None


def _validate_busy_intervals(
    busy_intervals: Iterable[BusyInterval],
) -> tuple[BusyInterval, ...]:
    validated: list[BusyInterval] = []
    for busy_start, busy_end in busy_intervals:
        if (
            busy_start.tzinfo is None
            or busy_start.utcoffset() is None
            or busy_end.tzinfo is None
            or busy_end.utcoffset() is None
        ):
            raise ValueError("Busy interval datetimes must be timezone-aware")
        if busy_end <= busy_start:
            raise ValueError("Busy intervals must end after they start")
        validated.append((busy_start, busy_end))
    return tuple(validated)


def slot_overlaps_busy(
    slot_start: datetime, busy_intervals: Sequence[BusyInterval]
) -> bool:
    """Return whether a 30-minute slot overlaps any busy interval."""
    slot_end = slot_start + APPOINTMENT_DURATION
    return any(
        slot_start < busy_end and slot_end > busy_start
        for busy_start, busy_end in busy_intervals
    )


def evaluate_availability(
    requested_start: datetime,
    busy_intervals: Iterable[BusyInterval],
    clinic_timezone: ZoneInfo,
) -> AvailabilityResult:
    """Apply clinic rules to already-fetched busy intervals.

    This function is deterministic and does not call Google Calendar.
    """
    requested_start = _normalize_request(requested_start, clinic_timezone)
    invalid_reason = _invalid_reason(requested_start)
    if invalid_reason:
        return AvailabilityResult(
            requested_start=requested_start,
            valid_request=False,
            available=False,
            nearest_available_start=None,
            reason=invalid_reason,
        )

    intervals = _validate_busy_intervals(busy_intervals)
    if not slot_overlaps_busy(requested_start, intervals):
        return AvailabilityResult(
            requested_start=requested_start,
            valid_request=True,
            available=True,
            nearest_available_start=None,
        )

    closing = _clinic_datetime(
        requested_start.date(), BUSINESS_CLOSE, clinic_timezone
    )
    candidate = requested_start + APPOINTMENT_DURATION
    while candidate + APPOINTMENT_DURATION <= closing:
        if not slot_overlaps_busy(candidate, intervals):
            return AvailabilityResult(
                requested_start=requested_start,
                valid_request=True,
                available=False,
                nearest_available_start=candidate,
                reason="The requested slot overlaps a busy calendar interval.",
            )
        candidate += APPOINTMENT_DURATION

    return AvailabilityResult(
        requested_start=requested_start,
        valid_request=True,
        available=False,
        nearest_available_start=None,
        reason="No remaining availability that day.",
    )


def _parse_google_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Google returned a timezone-naive datetime: {value}")
    return parsed


def fetch_busy_intervals(
    service: Any,
    calendar_id: str,
    day: date,
    clinic_timezone: ZoneInfo,
) -> tuple[BusyInterval, ...]:
    """Fetch the clinic's busy intervals for one business day via FreeBusy."""
    day_start = _clinic_datetime(day, BUSINESS_OPEN, clinic_timezone)
    day_end = _clinic_datetime(day, BUSINESS_CLOSE, clinic_timezone)
    response = (
        service.freebusy()
        .query(
            body={
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "timeZone": clinic_timezone.key,
                "items": [{"id": calendar_id}],
            }
        )
        .execute()
    )

    calendar_result = response.get("calendars", {}).get(calendar_id)
    if calendar_result is None:
        raise RuntimeError(
            "Google FreeBusy response did not include the clinic calendar"
        )

    errors = calendar_result.get("errors", [])
    if errors:
        reasons = ", ".join(error.get("reason", "unknown error") for error in errors)
        raise RuntimeError(f"Google FreeBusy calendar error: {reasons}")

    return tuple(
        (
            _parse_google_datetime(interval["start"]),
            _parse_google_datetime(interval["end"]),
        )
        for interval in calendar_result.get("busy", [])
    )


def check_calendar_availability(
    requested_start: datetime,
    service: Any,
    calendar_id: str,
    clinic_timezone: ZoneInfo,
) -> AvailabilityResult:
    """Validate a request, query FreeBusy, and calculate same-day availability."""
    normalized_start = _normalize_request(requested_start, clinic_timezone)
    invalid_reason = _invalid_reason(normalized_start)
    if invalid_reason:
        return evaluate_availability(normalized_start, (), clinic_timezone)

    busy_intervals = fetch_busy_intervals(
        service,
        calendar_id,
        normalized_start.date(),
        clinic_timezone,
    )
    return evaluate_availability(
        normalized_start,
        busy_intervals,
        clinic_timezone,
    )
