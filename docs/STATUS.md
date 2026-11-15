# ZKS95 VPN

Коммерческая VPN-платформа, разработка по [техническому заданию](SPECIFICATION.txt).

Репозиторий: https://github.com/kzolotarev95/zks95-vpn. Основная ветка: `main`.

## Статус

Разработка начата с пустого репозитория. **Текущий этап: сайт, кабинет, административная панель, биллинг, Telegram-бот и Mini App. Реальные платежи требуют ключей провайдеров и подключённой VPN-панели.**

Реализовано:

- FastAPI, SQLAlchemy 2 и первая Alembic-миграция: users, sessions, roles, admin membership, plans, orders, subscriptions и audit logs.
- Регистрация / вход / выход, Argon2id, отзываемые HttpOnly-сессии, проверка Origin, доверенные Host, распределённые Redis rate limits с отказом при недоступности Redis.
- Каталог тарифов, заказы с идемпотентностью, фиксированной стоимостью / условиями и изоляцией между пользователями, чтение подписок. **Заказ не активирует VPN.**
- Next.js / React / TypeScript / Tailwind / shadcn-compatible Button / Framer Motion: адаптивный Black / Gold сайт, FAQ, регистрация и личный кабинет с реальными данными API. CSP с nonce.
- Docker Compose: nginx, web, api, PostgreSQL 17, Redis; healthchecks, внутренние сети, постоянные volumes, production HTTPS-конфигурация.
- Ubuntu install / update / health-check / uninstall, PostgreSQL backup и план восстановления. Удаление не удаляет пользовательские volumes.
- GitHub Actions: Python 3.13 / PostgreSQL, lint, TypeScript, Next.js build, миграции, Gitleaks, Docker smoke test. Отдельный workflow публикации образов GHCR по тегам; релизов ещё нет.

Добавлены `/admin`, отдельные административные сессии, RBAC, сводка, пользователи, тарифы, заказы, подписки, аудит, настройки Telegram и раздел оплаты. При установке создаётся `admin/admin`, пароль можно сменить в панели; минимальная длина пароля — 5 символов. aiogram worker поддерживает анимированное приветствие, inline-меню, Mini App, Telegram Stars, аккаунты, тарифы, заказы и привязку сайта к Telegram. Сайт открывает ЮKassa, webhook проверяет платёж через API, а после подтверждения общий Billing service запускает выдачу доступа через 3x-ui или Remnawave. Mini App доступен по `/miniapp/`, HMAC initData проверяется на API. [Создание администратора, VPN-панели и подключение бота](ADMIN.md).

Не реализованы: VPN Node Agent и протоколы, устройства, рефералы, промокоды, уведомления, Celery и мониторинг. Подтверждение email и восстановление пароля также впереди. Подтверждение email и восстановление пароля также впереди.

## Проверки

Для этапа администратора / Telegram / VPN-панелей локально проходят 40 тестов: 2FA replay, RBAC, отзыв сессий, admin/admin без OTP, смена пароля, шифрование токена, одноразовые ссылки, handlers aiogram, адаптеры 3x-ui / Remnawave, повторная выдача после потерянного ответа, отзыв клиента и истечение срока, миграция старых пользователей / сессий и сохранение ключей при повторном обновлении. Проверены Ruff, TypeScript, ESLint и production build. Настоящие панели и токен Telegram проверяются владельцем после настройки.

Локально (Windows / Python 3.12 / Node 24): 40 backend-тестов, Ruff lint / format, миграции upgrade → check → downgrade → upgrade и повторный seed на SQLite, TypeScript / ESLint, production Next.js build, npm audit (0 уязвимостей), синтаксис Bash. В браузере проверены регистрация → выбор тарифа → сохранение заказа → перезагрузка → выход → повторный вход.

В GitHub Actions также прошли backend-тесты на Python 3.13 / PostgreSQL 17, миграции и полный Docker Compose smoke test: сборка API, web и Mini App, старт семи контейнеров, healthchecks, чтение каталога из PostgreSQL и загрузка сайта через nginx. Установка системных пакетов на чистую Ubuntu VPS, production HTTPS и реальная VPN-связь пока не подтверждены.

## Быстрый запуск на Ubuntu

```bash
git clone https://github.com/kzolotarev95/zks95-vpn.git
cd zks95-vpn
sudo bash scripts/install.sh
```

При отсутствии `.env` установщик создаёт его со случайным паролем БД. Development доступен на VPS по http://localhost:8080; для удалённого просмотра используйте SSH-туннель. Для production сначала настройте домен и TLS, заполните `.env`, затем `sudo bash scripts/install.sh --production`. [Подробная инструкция](DEPLOYMENT.md).

## Локальная разработка без Docker

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate; Windows: .venv\Scripts\Activate.ps1
pip install -c requirements.lock -e '.[dev]'
```

Задайте переменные окружения `DATABASE_URL=sqlite:///local.sqlite3`, `PUBLIC_URL=http://localhost:3000`, `ENVIRONMENT=development`, `RATE_LIMIT_ENABLED=false` (только локально). Затем:

```bash
alembic upgrade head
python -m app.cli seed
uvicorn app.main:app --host 127.0.0.1 --port 8000
# В другом терминале:
cd apps/web
npm ci
npm run dev
```

API — http://127.0.0.1:8000/api/docs; сайт — http://localhost:3000. SQLite служит только для локальных проверок, целевая БД — PostgreSQL. Readiness без Redis не пройдёт; ливнес и сценарии аккаунта доступны с локально отключёнными лимитами.

Проверки: `pytest -q`, `ruff check backend migrations scripts/validate-env.py`, `npm run lint`, `npm run typecheck`, `npm run build`. Python 3.13 используется в Docker / CI; 3.12 поддерживается для локальной проверки.

## Настройки

Сейчас обязательны: случайный `POSTGRES_PASSWORD`, `APP_ENCRYPTION_KEY`, `BOT_SERVICE_TOKEN` (генерируются установщиком); для внешнего запуска — `DOMAIN`, `PUBLIC_URL`, `TRUSTED_HOSTS`, TLS-сертификат и `COOKIE_SECURE=true`. Telegram и ЮKassa настраиваются в `/admin` → Telegram-бот / Оплата. Для чеков включите фискализацию и укажите корректный VAT code в `.env`. Не передавайте токены в чат или Git.

- [Архитектура](ARCHITECTURE.md)
- [Этапы и внешние настройки](ROADMAP.md)

Секреты запрещено коммитить. Файлы `.env`, резервные копии и закрытые ключи исключены из Git.
