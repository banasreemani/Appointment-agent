import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from calendar_availability import evaluate_availability


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


def clinic_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(
        tzinfo=CLINIC_TIMEZONE
    )


class AvailabilityRulesTest(unittest.TestCase):
    def evaluate(self, requested: str, busy: list[tuple[str, str]]):
        intervals = [
            (clinic_time(start), clinic_time(end)) for start, end in busy
        ]
        return evaluate_availability(
            clinic_time(requested), intervals, CLINIC_TIMEZONE
        )

    def test_requested_slot_is_free(self):
        result = self.evaluate("2026-08-17 10:00", [])

        self.assertTrue(result.valid_request)
        self.assertTrue(result.available)
        self.assertIsNone(result.nearest_available_start)

    def test_requested_slot_is_busy_and_next_slot_is_free(self):
        result = self.evaluate(
            "2026-08-17 10:00",
            [("2026-08-17 10:00", "2026-08-17 10:30")],
        )

        self.assertFalse(result.available)
        self.assertEqual(
            result.nearest_available_start, clinic_time("2026-08-17 10:30")
        )

    def test_multiple_consecutive_busy_slots(self):
        result = self.evaluate(
            "2026-08-17 14:00",
            [
                ("2026-08-17 14:00", "2026-08-17 14:30"),
                ("2026-08-17 14:30", "2026-08-17 15:00"),
            ],
        )

        self.assertFalse(result.available)
        self.assertEqual(
            result.nearest_available_start, clinic_time("2026-08-17 15:00")
        )

    def test_non_aligned_busy_event_overlaps_two_slots(self):
        result = self.evaluate(
            "2026-08-17 14:00",
            [("2026-08-17 14:15", "2026-08-17 14:45")],
        )

        self.assertFalse(result.available)
        self.assertEqual(
            result.nearest_available_start, clinic_time("2026-08-17 15:00")
        )

    def test_weekend_requests_are_rejected(self):
        for requested in ("2026-08-15 10:00", "2026-08-16 10:00"):
            with self.subTest(requested=requested):
                result = self.evaluate(requested, [])
                self.assertFalse(result.valid_request)
                self.assertFalse(result.available)
                self.assertIsNone(result.nearest_available_start)

    def test_before_opening_is_rejected(self):
        result = self.evaluate("2026-08-17 08:30", [])

        self.assertFalse(result.valid_request)
        self.assertIn("before", result.reason.lower())

    def test_1800_is_rejected(self):
        result = self.evaluate("2026-08-17 18:00", [])

        self.assertFalse(result.valid_request)
        self.assertIn("before", result.reason.lower())

    def test_slot_ending_after_close_is_rejected(self):
        result = self.evaluate("2026-08-17 17:45", [])

        self.assertFalse(result.valid_request)
        self.assertIn("end after", result.reason.lower())

    def test_non_boundary_start_is_rejected(self):
        result = self.evaluate("2026-08-17 10:15", [])

        self.assertFalse(result.valid_request)
        self.assertIn("30-minute boundary", result.reason)

    def test_1730_is_the_final_valid_slot(self):
        result = self.evaluate("2026-08-17 17:30", [])

        self.assertTrue(result.valid_request)
        self.assertTrue(result.available)

    def test_no_remaining_availability_that_day(self):
        result = self.evaluate(
            "2026-08-17 17:30",
            [("2026-08-17 17:30", "2026-08-17 18:00")],
        )

        self.assertTrue(result.valid_request)
        self.assertFalse(result.available)
        self.assertIsNone(result.nearest_available_start)
        self.assertEqual(result.reason, "No remaining availability that day.")


if __name__ == "__main__":
    unittest.main()
