"""Isolated Telegram connectivity handlers for BrightCare Clinic."""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


LOGGER = logging.getLogger(__name__)
START_RESPONSE = "BrightCare Clinic bot is online."
NON_TEXT_RESPONSE = "Please send a text message."


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
    """Echo a deterministic acknowledgement for ordinary text."""
    del context
    log_incoming_message(update)
    message = update.effective_message
    if message and message.text is not None:
        await message.reply_text(f"You said: {message.text}")


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


def build_telegram_application(token: str) -> Application:
    """Build the long-polling application without starting it."""
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT, text_handler))
    application.add_handler(MessageHandler(~filters.TEXT, non_text_handler))
    application.add_error_handler(error_handler)
    return application
