"""Run the BrightCare Clinic Telegram connectivity bot using long polling."""

import logging
import sys

from telegram import Update
from telegram.error import TelegramError

from calendar_availability import load_calendar_config
from calendar_booking import build_booking_calendar_service
from conversation_state import InMemoryConversationStore
from email_sender import SmtpConfirmationEmailSender, load_email_config
from environment_config import required_environment_variable
from intent_parser import build_gemini_client, load_intent_config
from telegram_bot import build_telegram_application
from telegram_booking_workflow import TelegramBookingWorkflow


LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    configure_logging()
    try:
        token = required_environment_variable("TELEGRAM_BOT_TOKEN")
        intent_config = load_intent_config()
        intent_client = build_gemini_client(intent_config)
        calendar_config = load_calendar_config()
        calendar_service = build_booking_calendar_service(calendar_config)
        email_sender = SmtpConfirmationEmailSender(load_email_config())
        booking_workflow = TelegramBookingWorkflow(
            state_store=InMemoryConversationStore(),
            calendar_service=calendar_service,
            calendar_id=calendar_config.calendar_id,
            clinic_timezone=calendar_config.timezone,
            confirmation_email_sender=email_sender.send_confirmation,
        )
        application = build_telegram_application(
            token,
            intent_client=intent_client,
            intent_model=intent_config.model,
            clinic_timezone=intent_config.clinic_timezone,
            booking_workflow=booking_workflow,
        )
    except (ValueError, OSError, TelegramError) as error:
        LOGGER.error("Telegram bot configuration error: %s", error)
        return 1

    LOGGER.info("BrightCare Clinic bot is starting with long polling.")
    LOGGER.info("Press Ctrl+C to stop the bot cleanly.")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except TelegramError as error:
        LOGGER.error("Telegram polling stopped because of a fatal error: %s", error)
        return 1

    LOGGER.info("BrightCare Clinic bot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
