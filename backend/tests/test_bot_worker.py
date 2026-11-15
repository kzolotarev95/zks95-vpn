import asyncio
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser
from app.bot import dispatcher


class RecordingBot(Bot):
    def __init__(self):
        super().__init__("123456789:" + "x" * 35)
        self.sent = []

    async def __call__(self, method, request_timeout=None):
        self.sent.append(method)
        if method.__api_method__ == "answerCallbackQuery":
            return True
        return Message(
            message_id=len(self.sent),
            date=datetime.now(UTC),
            chat=Chat(id=10001, type="private"),
            text=method.text,
        )


class BackendStub:
    def __init__(self):
        self.calls = []

    async def call(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == "/orders":
            return {"id": "order-1234", "plan_name": "Месяц", "amount_minor": 19900}
        if path.endswith("/snapshot"):
            return {"subscriptions": [], "orders": [], "plans": [], "email": None}
        return {"user_id": "test-user"}


def test_start_and_purchase_call_backend_and_do_not_claim_paid_access():
    async def scenario():
        bot, backend = RecordingBot(), BackendStub()
        dp = dispatcher(backend, {})
        user = TelegramUser(id=10001, is_bot=False, first_name="Tester")
        message = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=10001, type="private"),
            from_user=user,
            text="/start",
        )
        await dp.feed_update(bot, Update(update_id=1, message=message))
        assert backend.calls[0][1] == "/account"
        assert "готовится к запуску" in bot.sent[-1].text
        query = CallbackQuery(
            id="callback-000000001",
            from_user=user,
            chat_instance="test-chat",
            message=message,
            data="buy:00000000-0000-0000-0000-000000000001",
        )
        await dp.feed_update(bot, Update(update_id=2, callback_query=query))
        assert backend.calls[-1][1] == "/orders"
        assert backend.calls[-1][2]["idempotency_key"] == "telegram-callback-000000001"
        assert "VPN-доступ не активирован" in bot.sent[-1].text
        await bot.session.close()

    asyncio.run(scenario())


def test_group_start_does_not_register_or_disclose_account():
    async def scenario():
        bot, backend = RecordingBot(), BackendStub()
        dp = dispatcher(backend, {})
        message = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=-10001, type="group"),
            from_user=TelegramUser(id=10001, is_bot=False, first_name="Tester"),
            text="/start",
        )
        await dp.feed_update(bot, Update(update_id=1, message=message))
        assert not backend.calls
        assert not bot.sent
        await bot.session.close()

    asyncio.run(scenario())
