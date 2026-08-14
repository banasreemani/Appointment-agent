"""Check one requested appointment time against the real clinic calendar."""

import argparse
import sys
from datetime import datetime

from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError

from calendar_availability import (
    build_calendar_service,
    check_calendar_availability,
    load_calendar_config,
)


LOCAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a BrightCare Clinic slot using Google Calendar FreeBusy."
    )
    parser.add_argument(
        "requested",
        help='requested clinic-local time, for example "2026-08-17 14:00"',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_calendar_config()
        requested_start = datetime.strptime(
            args.requested, LOCAL_DATETIME_FORMAT
        ).replace(tzinfo=config.timezone)
        service = build_calendar_service(config)
        result = check_calendar_availability(
            requested_start,
            service,
            config.calendar_id,
            config.timezone,
        )
    except (ValueError, OSError, RuntimeError, GoogleAuthError, HttpError) as error:
        print(f"Unable to check availability: {error}", file=sys.stderr)
        return 1

    print(f"Requested slot: {result.requested_start:{LOCAL_DATETIME_FORMAT}}")
    print(f"Available: {'Yes' if result.available else 'No'}")

    if not result.valid_request:
        print(f"Result: Rejected - {result.reason}")
    elif not result.available and result.nearest_available_start is not None:
        print(
            "Nearest available slot: "
            f"{result.nearest_available_start:{LOCAL_DATETIME_FORMAT}}"
        )
    elif not result.available:
        print("Nearest available slot: None")
        print(f"Result: {result.reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
