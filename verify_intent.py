"""Run one standalone BrightCare intent extraction against Gemini."""

import argparse
import json
import sys
from datetime import datetime

from intent_parser import (
    IntentExtractionError,
    build_gemini_client,
    extract_intent,
    load_intent_config,
)


LOCAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a structured BrightCare Clinic intent."
    )
    parser.add_argument("message")
    parser.add_argument(
        "--reference",
        help=(
            "optional fixed clinic-local reference datetime in YYYY-MM-DD HH:MM "
            "format"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_intent_config()
        if args.reference:
            reference_datetime = datetime.strptime(
                args.reference,
                LOCAL_DATETIME_FORMAT,
            ).replace(tzinfo=config.clinic_timezone)
        else:
            reference_datetime = datetime.now(config.clinic_timezone)

        client = build_gemini_client(config)
        result = extract_intent(
            message=args.message,
            reference_datetime=reference_datetime,
            clinic_timezone=config.clinic_timezone,
            client=client,
            model=config.model,
        )
    except (ValueError, OSError, IntentExtractionError) as error:
        print(f"Unable to extract intent: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            result.model_dump(mode="json", exclude_none=True),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
