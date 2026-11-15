# План ZKS95 VPN

Источник требований: [SPECIFICATION.txt](SPECIFICATION.txt). Работа идёт в `main` репозитория `kzolotarev95/zks95-vpn`.

1. Проверка репозитория, структура, архитектура.
2. Docker: PostgreSQL, Redis, API, Next.js, nginx; изоляция и healthchecks.
3. API: миграции, регистрация, сессии, RBAC, тарифы, заказы, подписки, аудит.
4. Публичный сайт и кабинет на общем API, Black / Gold.
5. Admin Panel: 2FA, управление пользователями, тарифами, подписками, серверами, аудит.
6. aiogram Bot: действия меню, уведомления и управление подключениями.
7. Mini App: Telegram initData и общий API.
8. Billing: ЮKassa, чеки, Stars, webhooks, идемпотентность и возвраты.
9. Node Agent: регистрация, heartbeat, подписанные команды и синхронизация.
10. Отдельные адаптеры VLESS Reality, WireGuard, AmneziaWG.
11. Ubuntu install / update / uninstall / health-check и backup / restore.
12. CI/CD, Docker images, release workflow.
13. Интеграционные проверки на чистой Ubuntu и реальных тестовых интеграциях.

Статус реализации и проверки отражается в README. Наличие каталога или интерфейса не означает готовность интеграции.

## Условия запуска интеграций

- Домен и Ubuntu VPS для control plane; отдельный VPN VPS для проверки ноды.
- Telegram bot token и username, URL Mini App.
- ЮKassa shop ID, secret key, сведения для чеков и тестовый магазин.
- SMTP для подтверждения адреса и восстановления доступа.
- Секреты хранятся только в `.env` / secret storage, не в Git или документации.

Реальные продажи и выпуск стабильного релиза возможны после проверки полного пути оплаты → подписки → подключения → отключения, восстановления резервной копии и проверки безопасности.
