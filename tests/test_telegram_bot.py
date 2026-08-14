import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from intent_parser import Intent, IntentExtractionError, IntentResult
from telegram_bot import (
    BOOKING_WORKFLOW_KEY,
    CLINIC_TIMEZONE_KEY,
    INTENT_CLIENT_KEY,
    INTENT_EXTRACTOR_KEY,
    INTENT_MODEL_KEY,
    NON_TEXT_RESPONSE,
    REFERENCE_DATETIME_PROVIDER_KEY,
    START_RESPONSE,
    non_text_handler,
    start_handler,
    text_handler,
)
from telegram_intent_responses import GREETING_RESPONSE, INTENT_ERROR_RESPONSE


def fake_update(text=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=456),
        effective_message=message,
    )


def fake_context(intent_extractor, booking_workflow=None):
    clinic_timezone = ZoneInfo("Asia/Kolkata")
    reference_datetime = datetime(
        2026, 8, 14, 12, 0, tzinfo=clinic_timezone
    )
    bot_data = {
        INTENT_CLIENT_KEY: object(),
        INTENT_MODEL_KEY: "test-model",
        CLINIC_TIMEZONE_KEY: clinic_timezone,
        INTENT_EXTRACTOR_KEY: intent_extractor,
        REFERENCE_DATETIME_PROVIDER_KEY: lambda: reference_datetime,
        BOOKING_WORKFLOW_KEY: booking_workflow or Mock(),
    }
    return SimpleNamespace(application=SimpleNamespace(bot_data=bot_data))


class TelegramHandlersTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_handler_acknowledges_bot_is_online(self):
        update = fake_update("/start")

        await start_handler(update, SimpleNamespace())

        update.effective_message.reply_text.assert_awaited_once_with(START_RESPONSE)

    async def test_text_handler_routes_parsed_intent(self):
        update = fake_update("hello")
        extractor = Mock(return_value=IntentResult(intent=Intent.GREETING))
        booking_workflow = Mock()
        booking_workflow.is_awaiting_email.return_value = False
        booking_workflow.handle_intent.return_value = GREETING_RESPONSE
        context = fake_context(extractor, booking_workflow)

        await text_handler(update, context)

        update.effective_message.reply_text.assert_awaited_once_with(
            GREETING_RESPONSE
        )
        extractor.assert_called_once()
        call_arguments = extractor.call_args.kwargs
        self.assertEqual(call_arguments["message"], "hello")
        self.assertEqual(call_arguments["model"], "test-model")
        self.assertEqual(
            call_arguments["reference_datetime"].isoformat(),
            "2026-08-14T12:00:00+05:30",
        )
        booking_workflow.handle_intent.assert_called_once_with(
            123,
            IntentResult(intent=Intent.GREETING),
        )

    async def test_text_handler_handles_parser_failure(self):
        update = fake_update("unclear request")
        booking_workflow = Mock()
        booking_workflow.is_awaiting_email.return_value = False
        extractor = Mock(
            side_effect=IntentExtractionError("invalid structured response")
        )

        with self.assertLogs("telegram_bot", level="ERROR"):
            await text_handler(
                update,
                fake_context(extractor, booking_workflow),
            )

        update.effective_message.reply_text.assert_awaited_once_with(
            INTENT_ERROR_RESPONSE
        )
        booking_workflow.handle_intent.assert_not_called()

    async def test_awaiting_email_bypasses_intent_parser(self):
        update = fake_update("jane@example.com")
        extractor = Mock()
        booking_workflow = Mock()
        booking_workflow.is_awaiting_email.return_value = True
        booking_workflow.handle_expected_email.return_value = "booking result"

        await text_handler(
            update,
            fake_context(extractor, booking_workflow),
        )

        extractor.assert_not_called()
        booking_workflow.handle_expected_email.assert_called_once_with(
            123,
            "jane@example.com",
        )
        update.effective_message.reply_text.assert_awaited_once_with(
            "booking result"
        )

    async def test_non_text_handler_responds_gracefully(self):
        update = fake_update()

        await non_text_handler(update, SimpleNamespace())

        update.effective_message.reply_text.assert_awaited_once_with(
            NON_TEXT_RESPONSE
        )


if __name__ == "__main__":
    unittest.main()
