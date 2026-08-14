import unittest
from datetime import date, datetime, time
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from calendar_availability import AvailabilityResult
from conversation_state import (
    ConversationState,
    ConversationStatus,
    InMemoryConversationStore,
)
from intent_parser import FAQType, Intent, IntentResult
from telegram_booking_workflow import (
    ASK_FOR_EMAIL_RESPONSE,
    CALENDAR_ERROR_RESPONSE,
    DECLINE_SLOT_RESPONSE,
    NO_AVAILABILITY_RESPONSE,
    TelegramBookingWorkflow,
)
from telegram_intent_responses import AFFIRM_RESPONSE


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")
MONDAY = date(2026, 8, 17)
REQUESTED_START = datetime(2026, 8, 17, 14, 0, tzinfo=CLINIC_TIMEZONE)
ALTERNATIVE_START = datetime(2026, 8, 17, 15, 0, tzinfo=CLINIC_TIMEZONE)


def booking_intent(hour=14, minute=0, email=None):
    return IntentResult(
        intent=Intent.BOOKING,
        requested_date=MONDAY,
        requested_time=time(hour, minute),
        email=email,
    )


def availability_result(
    *,
    requested_start=REQUESTED_START,
    valid_request=True,
    available=False,
    nearest_available_start=ALTERNATIVE_START,
    reason=None,
):
    return AvailabilityResult(
        requested_start=requested_start,
        valid_request=valid_request,
        available=available,
        nearest_available_start=nearest_available_start,
        reason=reason,
    )


def make_workflow(result=None, checker=None):
    store = InMemoryConversationStore()
    if checker is None:
        checker = Mock(return_value=result)
    service = Mock()
    workflow = TelegramBookingWorkflow(
        state_store=store,
        calendar_service=service,
        calendar_id="clinic-calendar",
        clinic_timezone=CLINIC_TIMEZONE,
        availability_checker=checker,
    )
    return workflow, store, checker, service


class TelegramBookingWorkflowTest(unittest.TestCase):
    def test_available_slot_awaits_confirmation(self):
        result = availability_result(
            available=True,
            nearest_available_start=None,
        )
        workflow, store, checker, _ = make_workflow(result)

        response = workflow.handle_intent(101, booking_intent())

        state = store.get(101)
        self.assertEqual(
            state.status, ConversationStatus.AWAITING_SLOT_CONFIRMATION
        )
        self.assertEqual(state.proposed_start, REQUESTED_START)
        self.assertEqual(
            response,
            "Monday at 2:00pm is available — shall I book that?",
        )
        checker.assert_called_once_with(
            REQUESTED_START,
            workflow.calendar_service,
            "clinic-calendar",
            CLINIC_TIMEZONE,
        )

    def test_busy_slot_stores_and_proposes_nearest_alternative(self):
        workflow, store, _, _ = make_workflow(availability_result())

        response = workflow.handle_intent(101, booking_intent())

        state = store.get(101)
        self.assertEqual(state.requested_start, REQUESTED_START)
        self.assertEqual(state.proposed_start, ALTERNATIVE_START)
        self.assertEqual(
            response,
            "2:00pm Monday isn't available. The nearest opening is "
            "3:00pm — shall I book that?",
        )

    def test_affirm_selects_stored_proposed_slot(self):
        workflow, store, _, _ = make_workflow(availability_result())
        workflow.handle_intent(101, booking_intent())

        workflow.handle_intent(101, IntentResult(intent=Intent.AFFIRM))

        self.assertEqual(store.get(101).selected_start, ALTERNATIVE_START)

    def test_affirm_transitions_to_awaiting_email(self):
        workflow, store, _, _ = make_workflow(availability_result())
        workflow.handle_intent(101, booking_intent())

        response = workflow.handle_intent(
            101,
            IntentResult(intent=Intent.AFFIRM),
        )

        self.assertEqual(
            store.get(101).status,
            ConversationStatus.AWAITING_EMAIL,
        )
        self.assertEqual(response, ASK_FOR_EMAIL_RESPONSE)

    def test_decline_clears_proposal_and_returns_to_idle(self):
        workflow, store, _, _ = make_workflow(availability_result())
        workflow.handle_intent(101, booking_intent())

        response = workflow.handle_intent(
            101,
            IntentResult(intent=Intent.DECLINE),
        )

        state = store.get(101)
        self.assertEqual(state.status, ConversationStatus.IDLE)
        self.assertIsNone(state.requested_start)
        self.assertIsNone(state.proposed_start)
        self.assertIsNone(state.selected_start)
        self.assertEqual(response, DECLINE_SLOT_RESPONSE)

    def test_affirm_while_idle_does_not_select_a_slot(self):
        workflow, store, checker, _ = make_workflow(availability_result())

        response = workflow.handle_intent(
            101,
            IntentResult(intent=Intent.AFFIRM),
        )

        state = store.get(101)
        self.assertEqual(state.status, ConversationStatus.IDLE)
        self.assertIsNone(state.selected_start)
        self.assertEqual(response, AFFIRM_RESPONSE)
        checker.assert_not_called()

    def test_new_booking_replaces_pending_proposal(self):
        checker = Mock(
            side_effect=[
                availability_result(),
                availability_result(
                    requested_start=datetime(
                        2026, 8, 17, 16, 0, tzinfo=CLINIC_TIMEZONE
                    ),
                    available=True,
                    nearest_available_start=None,
                ),
            ]
        )
        workflow, store, _, _ = make_workflow(checker=checker)
        workflow.handle_intent(101, booking_intent())

        workflow.handle_intent(101, booking_intent(hour=16))

        state = store.get(101)
        new_start = datetime(2026, 8, 17, 16, 0, tzinfo=CLINIC_TIMEZONE)
        self.assertEqual(state.requested_start, new_start)
        self.assertEqual(state.proposed_start, new_start)
        self.assertIsNone(state.selected_start)
        self.assertEqual(checker.call_count, 2)

    def test_no_remaining_same_day_availability_returns_to_idle(self):
        result = availability_result(
            nearest_available_start=None,
            reason="No remaining availability that day.",
        )
        workflow, store, _, _ = make_workflow(result)

        response = workflow.handle_intent(101, booking_intent())

        self.assertEqual(store.get(101).status, ConversationStatus.IDLE)
        self.assertEqual(response, NO_AVAILABILITY_RESPONSE)

    def test_weekend_request_is_rejected_without_freebusy_query(self):
        service = Mock()
        workflow = TelegramBookingWorkflow(
            state_store=InMemoryConversationStore(),
            calendar_service=service,
            calendar_id="clinic-calendar",
            clinic_timezone=CLINIC_TIMEZONE,
        )
        saturday = IntentResult(
            intent=Intent.BOOKING,
            requested_date=date(2026, 8, 15),
            requested_time=time(10, 0),
        )

        response = workflow.handle_intent(101, saturday)

        self.assertEqual(response, "The clinic is closed on weekends.")
        self.assertEqual(
            workflow.state_store.get(101).status,
            ConversationStatus.IDLE,
        )
        service.freebusy.assert_not_called()

    def test_outside_hours_request_is_rejected_without_freebusy_query(self):
        service = Mock()
        workflow = TelegramBookingWorkflow(
            state_store=InMemoryConversationStore(),
            calendar_service=service,
            calendar_id="clinic-calendar",
            clinic_timezone=CLINIC_TIMEZONE,
        )

        response = workflow.handle_intent(101, booking_intent(hour=18))

        self.assertEqual(
            response,
            "The requested slot must start before the clinic closes at 18:00.",
        )
        service.freebusy.assert_not_called()

    def test_state_is_isolated_by_telegram_user_id(self):
        workflow, store, _, _ = make_workflow(availability_result())

        workflow.handle_intent(101, booking_intent())
        workflow.handle_intent(202, IntentResult(intent=Intent.AFFIRM))

        self.assertEqual(
            store.get(101).status,
            ConversationStatus.AWAITING_SLOT_CONFIRMATION,
        )
        self.assertEqual(store.get(101).proposed_start, ALTERNATIVE_START)
        self.assertEqual(store.get(202).status, ConversationStatus.IDLE)
        self.assertIsNone(store.get(202).selected_start)

    def test_existing_faq_behavior_is_preserved(self):
        workflow, store, checker, _ = make_workflow(availability_result())

        response = workflow.handle_intent(
            101,
            IntentResult(intent=Intent.FAQ, faq_type=FAQType.LOCATION),
        )

        self.assertEqual(
            response,
            "BrightCare Clinic is located at 12 Orchard Rd.",
        )
        self.assertEqual(store.get(101).status, ConversationStatus.IDLE)
        checker.assert_not_called()

    def test_calendar_failure_is_graceful_and_preserves_existing_state(self):
        checker = Mock(side_effect=RuntimeError("FreeBusy unavailable"))
        workflow, store, _, _ = make_workflow(checker=checker)
        existing_state = ConversationState(
            user_id=101,
            status=ConversationStatus.AWAITING_SLOT_CONFIRMATION,
            requested_start=REQUESTED_START,
            proposed_start=ALTERNATIVE_START,
        )
        store.save(existing_state)

        with self.assertLogs("telegram_booking_workflow", level="ERROR"):
            response = workflow.handle_intent(101, booking_intent(hour=16))

        self.assertEqual(response, CALENDAR_ERROR_RESPONSE)
        self.assertEqual(store.get(101), existing_state)

    def test_email_from_booking_intent_is_stored_without_booking(self):
        workflow, store, _, _ = make_workflow(availability_result())

        workflow.handle_intent(
            101,
            booking_intent(email="jane@example.com"),
        )

        self.assertEqual(store.get(101).patient_email, "jane@example.com")


if __name__ == "__main__":
    unittest.main()
