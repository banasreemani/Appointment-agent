"""Verify read-only access to a Google Calendar using a service account."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
EVENT_LIMIT = 5


def required_environment_variable(name: str) -> str:
    """Return a required environment variable or exit with a helpful message."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    try:
        calendar_id = required_environment_variable("GOOGLE_CALENDAR_ID")
        credential_file = Path(
            required_environment_variable("GOOGLE_SERVICE_ACCOUNT_FILE")
        ).expanduser()

        if not credential_file.is_file():
            raise ValueError(f"Service-account file not found: {credential_file}")

        credentials = service_account.Credentials.from_service_account_file(
            credential_file,
            scopes=SCOPES,
        )
        calendar = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

        now = datetime.now(timezone.utc).isoformat()
        result = (
            calendar.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=EVENT_LIMIT,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except (ValueError, OSError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    except HttpError as error:
        print(f"Google Calendar API error: {error}", file=sys.stderr)
        return 1

    events = result.get("items", [])
    print(f"Connected successfully. Found {len(events)} upcoming event(s).")

    for event in events:
        start = event.get("start", {})
        start_value = start.get("dateTime", start.get("date", "Unknown start"))
        summary = event.get("summary", "(No title)")
        print(f"- {start_value}: {summary}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
