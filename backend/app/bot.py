"""aiogram long polling worker. All platform state is accessed through Backend API."""

import asyncio
import contextlib
import logging
import time
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramConflictError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class BackendError(Exception):
    pass


class Backend:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def call(self, method: str, path: str, data: dict | None = None):
        try:
            response = await self.client.request(method, "/api/v1/internal/bot" + path, json=data)
            if response.status_code >= 400:
                detail = response.json().get("detail")
                raise BackendError(detail if isinstance(detail, str) else "Попробуйте позже")
            return response.json() if response.status_code != 204 else None
        except (httpx.HTTPError, ValueError):
            raise BackendError("Сервис временно недоступен. Попробуйте позже") from None


def menu(runtime: dict | None = None) -> InlineKeyboardMarkup:
    items = [
        ("🏠 Главная", "home"),
        ("🔐 Мои подключения", "connections"),
        ("🌍 Локации", "locations"),
        ("💎 Выбрать тариф", "plans"),
        ("📦 Подписки", "subs"),
        ("📊 Статистика", "stats"),
        ("🎁 Реферальная программа", "ref"),
        ("⚙️ Настройки", "settings"),
        ("💬 Поддержка", "support"),
    ]
    rows = [
        [
            InlineKeyboardButton(text=title, callback_data=action)
            for title, action in items[index : index + 2]
        ]
        for index in range(0, len(items), 2)
    ]
    if runtime and runtime.get("miniapp_url"):
        rows.insert(
            1,
            [
                InlineKeyboardButton(
                    text="✨ Открыть Mini App", web_app=WebAppInfo(url=runtime["miniapp_url"])
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_section(action: str, snapshot: dict) -> str:
    subscriptions = snapshot["subscriptions"]
    active = [sub for sub in subscriptions if sub["status"] == "active"]
    if action == "home":
        return (
            "✨ ZKS95 VPN · личное пространство\n\n"
            f"Активных подписок: {len(active)}\nЗаказов: {len(snapshot['orders'])}\n\n"
            "Выберите тариф, оплатите через ЮKassa или Telegram Stars и получите VPN-доступ "
            "после подтверждения. Платформа готовится к запуску новых локаций."
        )
    if action == "subs":
        if not subscriptions:
            return "📦 Подписок пока нет. Выберите тариф в меню."
        labels = {"active": "активна", "expired": "истекла", "revoked": "отозвана"}
        return "📦 Подписки\n\n" + "\n".join(
            f"{sub['plan_name']} · {labels.get(sub['status'], sub['status'])} · "
            f"до {sub['expires_at'][:10]}"
            for sub in subscriptions[:20]
        )
    if action == "connections":
        links = [sub for sub in active if sub.get("connection_url")]
        if not links:
            return (
                "🔐 Доступных подключений пока нет. После активации здесь появится ссылка подписки."
            )
        return "🔐 Мои подключения\n\n" + "\n\n".join(
            f"{sub['plan_name']} · до {sub['expires_at'][:10]}\n{sub['connection_url']}"
            for sub in links[:10]
        )
    if action == "locations":
        return "🌍 Локации\n\nДоступные серверы появятся здесь после проверки VPN-панелей."
    if action == "stats":
        used_bytes = sum(int(sub.get("used_bytes") or 0) for sub in active)
        return (
            f"📊 Ваш аккаунт\n\nЗаказов в последней истории: {len(snapshot['orders'])}\n"
            f"Активных подписок: {len(active)}\nИспользовано VPN-трафика: {used_bytes} байт"
        )
    if action == "ref":
        return "🎁 Реферальная программа ещё готовится. Начислений и приглашений пока нет."
    return (
        "⚙️ Аккаунт\n\n"
        + (snapshot.get("email") or "Вход через Telegram")
        + "\nЧтобы связать сайт и Telegram, сначала откройте ссылку подключения в личном кабинете. "
        "Уже созданные отдельные аккаунты автоматически не объединяются."
    )


def dispatcher(backend: Backend, runtime: dict) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message):
        if not message.from_user:
            return
        payload = (message.text or "").partition(" ")[2]
        try:
            with contextlib.suppress(Exception):
                await message.bot.send_chat_action(
                    chat_id=message.chat.id, action=ChatAction.TYPING
                )
            await backend.call(
                "POST",
                "/account",
                {
                    "telegram_id": message.from_user.id,
                    "username": message.from_user.username,
                    "display_name": message.from_user.full_name[:128],
                    "link_token": payload[5:] if payload.startswith("link_") else None,
                },
            )
            snapshot = await backend.call("GET", f"/users/{message.from_user.id}/snapshot")
            await message.answer(render_section("home", snapshot), reply_markup=menu(runtime))
        except BackendError as exc:
            await message.answer(str(exc))

    @dp.message(Command("terms"), F.chat.type == "private")
    async def terms(message: Message):
        await message.answer(
            "📄 Условия оплаты\n\n"
            "Оплата тарифа подтверждается только после уведомления Telegram Stars или ЮKassa. "
            "Доступ выдаётся автоматически после подтверждения. По вопросам возврата обратитесь "
            "в поддержку через кнопку меню."
        )

    @dp.message(Command("support"), F.chat.type == "private")
    async def support_command(message: Message):
        username = runtime.get("support_username")
        if username:
            await message.answer(f"💬 Поддержка: https://t.me/{username}")
        else:
            await message.answer("💬 Контакт поддержки ещё не настроен администратором.")

    @dp.callback_query()
    async def callback(query: CallbackQuery):
        if not query.message or query.message.chat.type != "private":
            await query.answer("Откройте личный чат с ботом")
            return
        await query.answer()
        action = query.data or "home"
        try:
            if action == "connections":
                snapshot = await backend.call("POST", f"/users/{query.from_user.id}/refresh")
            else:
                snapshot = await backend.call("GET", f"/users/{query.from_user.id}/snapshot")
            if action == "plans":
                buttons = [
                    [
                        InlineKeyboardButton(
                            text=f"{plan['name']} · {plan['price_minor'] / 100:g} ₽",
                            callback_data=f"buy:{plan['id']}",
                        )
                    ]
                    for plan in snapshot["plans"]
                ]
                buttons.append([InlineKeyboardButton(text="← Главное меню", callback_data="home")])
                await query.message.answer(
                    "💎 Выберите тариф. Сайт принимает оплату через ЮKassa, а в Telegram "
                    "доступна оплата Stars.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                )
            elif action.startswith("buy:"):
                order = await backend.call(
                    "POST",
                    "/orders",
                    {
                        "telegram_id": query.from_user.id,
                        "plan_id": action[4:],
                        "idempotency_key": f"telegram-{query.id}",
                    },
                )
                invoice = None
                if order.get("stars_price"):
                    invoice = await backend.call(
                        "POST",
                        f"/orders/{order['id']}/stars-invoice",
                        {"telegram_id": query.from_user.id},
                    )
                if invoice and invoice.get("stars_price"):
                    await query.message.answer_invoice(
                        title=invoice["title"],
                        description=invoice["description"],
                        payload=invoice["payload"],
                        provider_token="",
                        currency="XTR",
                        prices=[
                            LabeledPrice(label=invoice["title"], amount=invoice["stars_price"])
                        ],
                    )
                else:
                    await query.message.answer(
                        f"Заказ {order['id'][:8]} создан. Для Telegram Stars администратору "
                        "нужно указать цену Stars для тарифа.\n"
                        "На сайте можно оплатить через ЮKassa. VPN-доступ не активирован "
                        "до подтверждения платежа.",
                        reply_markup=menu(runtime),
                    )
            elif action == "support":
                username = runtime.get("support_username")
                keyboard = (
                    InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Написать в поддержку", url=f"https://t.me/{username}"
                                )
                            ]
                        ]
                    )
                    if username
                    else menu(runtime)
                )
                await query.message.answer(
                    "💬 Поддержка"
                    if username
                    else "💬 Владелец сервиса пока не указал контакт поддержки.",
                    reply_markup=keyboard,
                )
            else:
                await query.message.answer(
                    render_section(action, snapshot), reply_markup=menu(runtime)
                )
        except BackendError as exc:
            await query.message.answer(str(exc), reply_markup=menu(runtime))

    @dp.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery):
        try:
            payload = query.invoice_payload
            if not payload.startswith("zks95:"):
                await query.answer(ok=False, error_message="Некорректный заказ")
                return
            result = await backend.call(
                "POST",
                "/stars/precheckout",
                {
                    "telegram_id": query.from_user.id,
                    "order_id": payload[6:],
                    "payload": payload,
                    "amount": query.total_amount,
                    "currency": query.currency,
                },
            )
            await query.answer(ok=bool(result.get("ok")), error_message=result.get("error"))
        except BackendError as exc:
            await query.answer(ok=False, error_message=str(exc))

    @dp.message(F.successful_payment, F.chat.type == "private")
    async def successful_payment(message: Message):
        payment = message.successful_payment
        if not payment:
            return
        try:
            payload = payment.invoice_payload
            await backend.call(
                "POST",
                "/stars/confirm",
                {
                    "telegram_id": message.from_user.id if message.from_user else 0,
                    "order_id": payload[6:]
                    if payload.startswith("zks95:")
                    else "00000000-0000-0000-0000-000000000000",
                    "telegram_payment_id": payment.telegram_payment_charge_id,
                    "amount": payment.total_amount,
                    "currency": payment.currency,
                    "payload": {
                        "invoice_payload": payload,
                        "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                    },
                },
            )
            await message.answer(
                "✅ Оплата подтверждена. VPN-доступ выдаётся, обновите раздел "
                "«Мои подключения» через пару секунд.",
                reply_markup=menu(runtime),
            )
        except BackendError as exc:
            await message.answer(str(exc), reply_markup=menu(runtime))

    @dp.message(F.chat.type == "private")
    async def other(message: Message):
        await message.answer(
            "Нажмите /start или выберите действие в меню.", reply_markup=menu(runtime)
        )

    return dp


async def run() -> None:
    settings = get_settings()
    if not settings.bot_service_token:
        raise SystemExit("BOT_SERVICE_TOKEN is missing. Run scripts/ensure-secrets.py.")
    bot = None
    token = None
    revision = 0
    offset = None
    runtime: dict = {}
    async with httpx.AsyncClient(
        base_url=settings.api_internal_url,
        timeout=15,
        headers={"X-Bot-Service-Token": settings.bot_service_token},
    ) as client:
        backend = Backend(client)
        dp = dispatcher(backend, runtime)
        try:
            while True:
                error = None
                try:
                    config = await backend.call("GET", "/config")
                    revision = config["revision"]
                    runtime.update(config)
                    next_token = config.get("token") if config["enabled"] else None
                    if next_token != token:
                        if bot:
                            await bot.session.close()
                        token, offset = next_token, None
                        bot = Bot(token) if token else None
                    # Private tmpfs in this container; contains only a health timestamp.
                    Path("/tmp/zks95-bot-health").write_text(str(time.time()))  # noqa: S108
                    if bot:
                        updates = await bot.get_updates(
                            offset=offset,
                            timeout=10,
                            allowed_updates=["message", "callback_query", "pre_checkout_query"],
                            request_timeout=20,
                        )
                        for update in updates:
                            await dp.feed_update(bot, update)
                            offset = update.update_id + 1
                    await backend.call(
                        "POST",
                        "/heartbeat",
                        {
                            "revision": revision,
                            "running": bot is not None,
                            "error": None,
                        },
                    )
                    if not bot:
                        await asyncio.sleep(5)
                except TelegramConflictError:
                    error = "telegram_conflict"
                except TelegramUnauthorizedError:
                    error = "telegram_unauthorized"
                except (TelegramAPIError, BackendError, ValueError):
                    error = "telegram_unavailable"
                except Exception:
                    # Do not expose URLs or credentials through tracebacks in container logs.
                    error = "telegram_unavailable"
                if error:
                    with contextlib.suppress(BackendError):
                        await backend.call(
                            "POST",
                            "/heartbeat",
                            {
                                "revision": revision,
                                "running": False,
                                "error": error,
                            },
                        )
                    logger.warning("Bot temporarily unavailable: %s", error)
                    await asyncio.sleep(5)
        finally:
            if bot:
                await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
