"""Explicitly confirm and create one real BrightCare Calendar appointment."""

import argparse
import sys
from datetime import datetime

from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError

from calendar_availability import APPOINTMENT_DURATION, load_calendar_config
from calendar_booking import build_booking_calendar_service, book_appointment


LOCAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one real BrightCare Clinic Google Calendar event."
    )
    parser.add_argument(
        "requested",
        help='appointment clinic-local time, for example "2026-08-17 15:00"',
    )
    parser.add_argument("patient_email")
    parser.add_argument("--patient-name")
    return parser.parse_args()


def format_appointment(start: datetime, end: datetime) -> str:
    return f"{start:{LOCAL_DATETIME_FORMAT}}–{end:%H:%M}"


def main() -> int:
    args = parse_args()
    try:
        config = load_calendar_config()
        appointment_start = datetime.strptime(
            args.requested, LOCAL_DATETIME_FORMAT
        ).replace(tzinfo=config.timezone)
    except (ValueError, OSError) as error:
        print(f"Unable to prepare booking: {error}", file=sys.stderr)
        return 1

    appointment_end = appointment_start + APPOINTMENT_DURATION
    print("Preparing to create a real Google Calendar appointment:")
    print(f"Appointment: {format_appointment(appointment_start, appointment_end)}")
    print(f"Patient email: {args.patient_email}")

    try:
        confirmation = input("Create this real Google Calendar appointment? [y/N] ")
    except EOFError:
        confirmation = ""

    if confirmation.strip().lower() != "y":
        print("Booking cancelled; no event was created.")
        return 0

    try:
        service = build_booking_calendar_service(config)
    except (ValueError, OSError, GoogleAuthError, HttpError) as error:
        print(f"Unable to prepare Google Calendar service: {error}", file=sys.stderr)
        return 1

    result = book_appointment(
        appointment_start=appointment_start,
        patient_email=args.patient_email,
        patient_name=args.patient_name,
        service=service,
        calendar_id=config.calendar_id,
        clinic_timezone=config.timezone,
    )

    if not result.success:
        print("Booking failed")
        print(
            "Appointment: "
            f"{format_appointment(result.appointment_start, result.appointment_end)}"
        )
        print(f"Reason: {result.reason}")
        return 1

    print("Booking successful")
    print(
        "Appointment: "
        f"{format_appointment(result.appointment_start, result.appointment_end)}"
    )
    print(f"Calendar event ID: {result.event_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
