# Telegram Mini App

Mini App разворачивается как отдельный Next.js-сервис по `/miniapp/`. При открытии из Telegram
он передаёт `initData` на API, где проверяется HMAC с токеном бота и создаётся отдельная Telegram-сессия.
Тарифы оплачиваются Telegram Stars; подтверждённый `successful_payment` обрабатывает тот же бот,
после чего общий Billing service меняет заказ на `paid` и запускает выдачу доступа через назначенную панель.
