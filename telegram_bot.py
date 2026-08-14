"""Isolated Telegram connectivity handlers for BrightCare Clinic."""

import asyncio
from datetime import datetime
import logging
from typing import Any, Callable
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from intent_parser import extract_intent
from telegram_booking_workflow import TelegramBookingWorkflow
from telegram_intent_responses import INTENT_ERROR_RESPONSE


LOGGER = logging.getLogger(__name__)
START_RESPONSE = "BrightCare Clinic bot is online."
NON_TEXT_RESPONSE = "Please send a text message."
INTENT_CLIENT_KEY = "intent_client"
INTENT_MODEL_KEY = "intent_model"
CLINIC_TIMEZONE_KEY = "clinic_timezone"
INTENT_EXTRACTOR_KEY = "intent_extractor"
REFERENCE_DATETIME_PROVIDER_KEY = "reference_datetime_provider"
BOOKING_WORKFLOW_KEY = "booking_workflow"


def log_incoming_message(update: Update) -> None:
    """Log useful identifiers and message text without retaining state."""
    user_id = update.effective_user.id if update.effective_user else "unknown"
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    message = update.effective_message
    text = message.text if message and message.text is not None else "<non-text>"
    LOGGER.info(
        "Incoming Telegram message user_id=%s chat_id=%s text=%r",
        user_id,
        chat_id,
        text,
    )


async def start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Acknowledge the Telegram /start command."""
    del context
    log_incoming_message(update)
    if update.effective_message:
        await update.effective_message.reply_text(START_RESPONSE)


async def text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Extract intent and return an application-owned deterministic response."""
    log_incoming_message(update)
    message = update.effective_message
    if not message or message.text is None:
        return

    dependencies = context.application.bot_data
    try:
        if update.effective_user is None:
            raise ValueError("Telegram update has no effective user")
        reference_datetime = dependencies[REFERENCE_DATETIME_PROVIDER_KEY]()
        result = await asyncio.to_thread(
            dependencies[INTENT_EXTRACTOR_KEY],
            message=message.text,
            reference_datetime=reference_datetime,
            clinic_timezone=dependencies[CLINIC_TIMEZONE_KEY],
            client=dependencies[INTENT_CLIENT_KEY],
            model=dependencies[INTENT_MODEL_KEY],
        )
        response = await asyncio.to_thread(
            dependencies[BOOKING_WORKFLOW_KEY].handle_intent,
            update.effective_user.id,
            result,
        )
    except Exception:
        LOGGER.exception("Unable to extract intent from Telegram message")
        response = INTENT_ERROR_RESPONSE

    await message.reply_text(response)


async def non_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Respond safely to message types outside this milestone's scope."""
    del context
    log_incoming_message(update)
    if update.effective_message:
        await update.effective_message.reply_text(NON_TEXT_RESPONSE)


async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Log polling or handler errors and allow polling to continue."""
    LOGGER.error(
        "Telegram polling or handler error for update %r: %s",
        update,
        context.error,
        exc_info=context.error,
    )


def build_telegram_application(
    token: str,
    *,
    intent_client: Any,
    intent_model: str,
    clinic_timezone: ZoneInfo,
    booking_workflow: TelegramBookingWorkflow,
    reference_datetime_provider: Callable[[], datetime] | None = None,
) -> Application:
    """Build the long-polling application without starting it."""
    application = Application.builder().token(token).build()
    application.bot_data[INTENT_CLIENT_KEY] = intent_client
    application.bot_data[INTENT_MODEL_KEY] = intent_model
    application.bot_data[CLINIC_TIMEZONE_KEY] = clinic_timezone
    application.bot_data[INTENT_EXTRACTOR_KEY] = extract_intent
    application.bot_data[BOOKING_WORKFLOW_KEY] = booking_workflow
    application.bot_data[REFERENCE_DATETIME_PROVIDER_KEY] = (
        reference_datetime_provider
        or (lambda: datetime.now(clinic_timezone))
    )
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT, text_handler))
    application.add_handler(MessageHandler(~filters.TEXT, non_text_handler))
    application.add_error_handler(error_handler)
    return application
