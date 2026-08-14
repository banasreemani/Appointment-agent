import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram_bot import (
    NON_TEXT_RESPONSE,
    START_RESPONSE,
    non_text_handler,
    start_handler,
    text_handler,
)


def fake_update(text=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=456),
        effective_message=message,
    )


class TelegramHandlersTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_handler_acknowledges_bot_is_online(self):
        update = fake_update("/start")

        await start_handler(update, SimpleNamespace())

        update.effective_message.reply_text.assert_awaited_once_with(START_RESPONSE)

    async def test_text_handler_echoes_message(self):
        update = fake_update("hello")

        await text_handler(update, SimpleNamespace())

        update.effective_message.reply_text.assert_awaited_once_with(
            "You said: hello"
        )

    async def test_non_text_handler_responds_gracefully(self):
        update = fake_update()

        await non_text_handler(update, SimpleNamespace())

        update.effective_message.reply_text.assert_awaited_once_with(
            NON_TEXT_RESPONSE
        )


if __name__ == "__main__":
    unittest.main()
