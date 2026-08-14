import unittest
from datetime import date, time

from intent_parser import FAQType, Intent, IntentResult
from telegram_intent_responses import (
    AFFIRM_RESPONSE,
    BOOKING_CLARIFICATION_RESPONSE,
    DECLINE_RESPONSE,
    GREETING_RESPONSE,
    OTHER_RESPONSE,
    response_for_intent,
)


class TelegramIntentResponsesTest(unittest.TestCase):
    def test_greeting_returns_welcome(self):
        result = IntentResult(intent=Intent.GREETING)

        self.assertEqual(response_for_intent(result), GREETING_RESPONSE)

    def test_location_faq_returns_fixed_address(self):
        result = IntentResult(intent=Intent.FAQ, faq_type=FAQType.LOCATION)

        self.assertEqual(
            response_for_intent(result),
            "BrightCare Clinic is located at 12 Orchard Rd.",
        )

    def test_hours_faq_returns_fixed_hours(self):
        result = IntentResult(intent=Intent.FAQ, faq_type=FAQType.HOURS)

        self.assertEqual(
            response_for_intent(result),
            "We're open Monday to Friday, 9:00am to 6:00pm.",
        )

    def test_complete_booking_is_acknowledged_without_booking(self):
        result = IntentResult(
            intent=Intent.BOOKING,
            requested_date=date(2026, 8, 17),
            requested_time=time(14, 0),
        )

        self.assertEqual(
            response_for_intent(result),
            "I understood that you'd like to book an appointment for "
            "Monday at 2:00pm.",
        )

    def test_incomplete_booking_requests_date_and_time(self):
        result = IntentResult(
            intent=Intent.BOOKING,
            requested_date=date(2026, 8, 17),
        )

        self.assertEqual(
            response_for_intent(result), BOOKING_CLARIFICATION_RESPONSE
        )

    def test_affirm_is_acknowledged_without_state_resolution(self):
        result = IntentResult(intent=Intent.AFFIRM)

        self.assertEqual(response_for_intent(result), AFFIRM_RESPONSE)

    def test_decline_is_acknowledged(self):
        result = IntentResult(intent=Intent.DECLINE)

        self.assertEqual(response_for_intent(result), DECLINE_RESPONSE)

    def test_other_returns_supported_scope(self):
        result = IntentResult(intent=Intent.OTHER)

        self.assertEqual(response_for_intent(result), OTHER_RESPONSE)


if __name__ == "__main__":
    unittest.main()
