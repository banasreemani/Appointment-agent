import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from intent_parser import (
    FAQType,
    Intent,
    IntentExtractionError,
    IntentResult,
    extract_intent,
)


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")
REFERENCE_DATETIME = datetime(
    2026,
    8,
    14,
    12,
    0,
    tzinfo=CLINIC_TIMEZONE,
)


class FakeModels:
    def __init__(self, payload):
        self.response_text = (
            payload if isinstance(payload, str) else json.dumps(payload)
        )
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.response_text)


class FakeClient:
    def __init__(self, parsed):
        self.models = FakeModels(parsed)


class IntentParserTest(unittest.TestCase):
    def extract(self, parsed, message="test message"):
        client = FakeClient(parsed)
        result = extract_intent(
            message=message,
            reference_datetime=REFERENCE_DATETIME,
            clinic_timezone=CLINIC_TIMEZONE,
            client=client,
            model="test-model",
        )
        return result, client

    def test_valid_structured_booking_result(self):
        result, _ = self.extract(
            {
                "intent": "BOOKING",
                "requested_date": "2026-08-17",
                "requested_time": "14:00",
                "email": None,
                "faq_type": None,
            }
        )

        self.assertEqual(result.intent, Intent.BOOKING)
        self.assertEqual(result.requested_date.isoformat(), "2026-08-17")
        self.assertEqual(result.requested_time.strftime("%H:%M"), "14:00")

    def test_faq_result(self):
        result, _ = self.extract(
            {
                "intent": "FAQ",
                "faq_type": "LOCATION",
            }
        )

        self.assertEqual(result.intent, Intent.FAQ)
        self.assertEqual(result.faq_type, FAQType.LOCATION)

    def test_affirm_result(self):
        result, _ = self.extract({"intent": "AFFIRM"}, "yes please")

        self.assertEqual(result.intent, Intent.AFFIRM)

    def test_decline_result(self):
        result, _ = self.extract({"intent": "DECLINE"}, "no thanks")

        self.assertEqual(result.intent, Intent.DECLINE)

    def test_greeting_result(self):
        result, _ = self.extract({"intent": "GREETING"}, "hello")

        self.assertEqual(result.intent, Intent.GREETING)

    def test_other_result(self):
        result, _ = self.extract({"intent": "OTHER"}, "What's the weather?")

        self.assertEqual(result.intent, Intent.OTHER)

    def test_booking_allows_missing_optional_fields(self):
        result, _ = self.extract({"intent": "BOOKING"}, "I need an appointment")

        self.assertEqual(result.intent, Intent.BOOKING)
        self.assertIsNone(result.requested_date)
        self.assertIsNone(result.requested_time)
        self.assertIsNone(result.email)

    def test_invalid_structured_output_is_handled_safely(self):
        with self.assertRaises(IntentExtractionError):
            self.extract({"intent": "FAQ", "faq_type": None})

    def test_reference_datetime_and_timezone_are_passed_correctly(self):
        utc_reference = datetime(2026, 8, 14, 6, 30, tzinfo=timezone.utc)
        client = FakeClient({"intent": "GREETING"})

        extract_intent(
            message="hello",
            reference_datetime=utc_reference,
            clinic_timezone=CLINIC_TIMEZONE,
            client=client,
            model="test-model",
        )

        call = client.models.calls[0]
        self.assertEqual(call["model"], "test-model")
        self.assertIn("2026-08-14T12:00:00+05:30", call["contents"])
        self.assertIn("Clinic weekday: Friday", call["contents"])
        self.assertIn("Clinic timezone: Asia/Kolkata", call["contents"])
        config = call["config"]
        self.assertEqual(
            config.response_json_schema,
            IntentResult.model_json_schema(),
        )
        self.assertIsNone(config.response_schema)
        self.assertIsNone(config.tools)
        self.assertTrue(config.automatic_function_calling.disable)

    def test_email_is_extracted_when_present(self):
        result, _ = self.extract(
            {
                "intent": "BOOKING",
                "requested_date": "2026-08-15",
                "requested_time": "10:30:00Z",
                "email": "jane@example.com",
            }
        )

        self.assertEqual(result.email, "jane@example.com")
        self.assertEqual(result.requested_time.strftime("%H:%M"), "10:30")
        self.assertIsNone(result.requested_time.tzinfo)


if __name__ == "__main__":
    unittest.main()
