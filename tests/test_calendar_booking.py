import unittest
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from calendar_booking import book_appointment


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")
CALENDAR_ID = "clinic-calendar@example.com"


def clinic_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(
        tzinfo=CLINIC_TIMEZONE
    )


class FakeRequest:
    def __init__(self, response=None, error=None, on_execute=None):
        self.response = response
        self.error = error
        self.on_execute = on_execute

    def execute(self):
        if self.on_execute:
            self.on_execute()
        if self.error:
            raise self.error
        return self.response


class FakeFreeBusyResource:
    def __init__(self, service):
        self.service = service

    def query(self, body):
        self.service.freebusy_query_body = body
        return FakeRequest(
            response={
                "calendars": {
                    CALENDAR_ID: {
                        "busy": self.service.busy_intervals,
                    }
                }
            },
            on_execute=lambda: self.service.call_order.append("freebusy"),
        )


class FakeEventsResource:
    def __init__(self, service):
        self.service = service

    def insert(self, calendarId, body):
        self.service.call_order.append("insert")
        self.service.insert_calls.append(
            {
                "calendarId": calendarId,
                "body": body,
            }
        )
        return FakeRequest(
            response=self.service.insert_response,
            error=self.service.insert_error,
        )


class FakeCalendarService:
    def __init__(self, busy_intervals=None, insert_response=None, insert_error=None):
        self.busy_intervals = busy_intervals or []
        self.insert_response = insert_response or {"id": "event-123"}
        self.insert_error = insert_error
        self.freebusy_query_body = None
        self.insert_calls = []
        self.call_order = []

    def freebusy(self):
        return FakeFreeBusyResource(self)

    def events(self):
        return FakeEventsResource(self)


class CalendarBookingTest(unittest.TestCase):
    def book(self, start: str, service: FakeCalendarService):
        return book_appointment(
            appointment_start=clinic_time(start),
            patient_email="test@example.com",
            patient_name="Test Patient",
            service=service,
            calendar_id=CALENDAR_ID,
            clinic_timezone=CLINIC_TIMEZONE,
        )

    def test_valid_free_slot_requests_event_creation(self):
        service = FakeCalendarService()

        result = self.book("2026-08-17 15:00", service)

        self.assertTrue(result.success)
        self.assertEqual(len(service.insert_calls), 1)

    def test_busy_slot_does_not_create_event(self):
        service = FakeCalendarService(
            busy_intervals=[
                {
                    "start": "2026-08-17T15:00:00+05:30",
                    "end": "2026-08-17T15:30:00+05:30",
                }
            ]
        )

        result = self.book("2026-08-17 15:00", service)

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "The requested slot is no longer available.")
        self.assertEqual(service.insert_calls, [])

    def test_weekend_does_not_create_event(self):
        service = FakeCalendarService()

        result = self.book("2026-08-15 15:00", service)

        self.assertFalse(result.success)
        self.assertIn("weekends", result.reason)
        self.assertIsNone(service.freebusy_query_body)
        self.assertEqual(service.insert_calls, [])

    def test_outside_business_hours_does_not_create_event(self):
        service = FakeCalendarService()

        result = self.book("2026-08-17 18:00", service)

        self.assertFalse(result.success)
        self.assertIn("before", result.reason)
        self.assertIsNone(service.freebusy_query_body)
        self.assertEqual(service.insert_calls, [])

    def test_event_insertion_failure_returns_clear_result(self):
        response = Mock(status=500, reason="Internal Server Error")
        response.getheaders.return_value = {}
        error = HttpError(
            response,
            b'{"error": {"message": "insert failed"}}',
        )
        service = FakeCalendarService(insert_error=error)

        result = self.book("2026-08-17 15:00", service)

        self.assertFalse(result.success)
        self.assertIsNone(result.event_id)
        self.assertIn("event insertion failed", result.reason)

    def test_success_contains_event_id_and_correct_times(self):
        service = FakeCalendarService(insert_response={"id": "created-event-id"})

        result = self.book("2026-08-17 15:00", service)

        self.assertTrue(result.success)
        self.assertEqual(result.event_id, "created-event-id")
        self.assertEqual(result.appointment_start, clinic_time("2026-08-17 15:00"))
        self.assertEqual(result.appointment_end, clinic_time("2026-08-17 15:30"))

        event_body = service.insert_calls[0]["body"]
        self.assertEqual(event_body["summary"], "BrightCare Clinic Appointment")
        self.assertEqual(event_body["start"]["timeZone"], "Asia/Kolkata")
        self.assertEqual(event_body["end"]["timeZone"], "Asia/Kolkata")
        self.assertIn("test@example.com", event_body["description"])
        self.assertNotIn("attendees", event_body)

    def test_availability_is_rechecked_immediately_before_insert(self):
        service = FakeCalendarService()

        result = self.book("2026-08-17 15:00", service)

        self.assertTrue(result.success)
        self.assertEqual(service.call_order, ["freebusy", "insert"])


if __name__ == "__main__":
    unittest.main()
