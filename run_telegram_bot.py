"""Run the BrightCare Clinic Telegram connectivity bot using long polling."""

import logging
import sys

from telegram import Update
from telegram.error import TelegramError

from environment_config import required_environment_variable
from telegram_bot import build_telegram_application


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
        application = build_telegram_application(token)
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
