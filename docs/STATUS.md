# ZKS95 VPN

Коммерческая VPN-платформа, разработка по [техническому заданию](docs/SPECIFICATION.txt).

Репозиторий: https://github.com/kzolotarev95/zks95-vpn. Основная ветка: `main`.

## Статус

Разработка начата с пустого репозитория. **Это первый рабочий этап, не готовый коммерческий VPN и не стабильный эксплуатационный релиз.**

Реализовано:

- FastAPI, SQLAlchemy 2 и первая Alembic-миграция: users, sessions, roles, admin membership, plans, orders, subscriptions и audit logs.
- Регистрация / вход / выход, Argon2id, отзываемые HttpOnly-сессии, проверка Origin, доверенные Host, распределённые Redis rate limits с отказом при недоступности Redis.
- Каталог тарифов, заказы с идемпотентностью, фиксированной стоимостью / условиями и изоляцией между пользователями, чтение подписок. **Заказ не активирует VPN.**
- Next.js / React / TypeScript / Tailwind / shadcn-compatible Button / Framer Motion: адаптивный Black / Gold сайт, FAQ, регистрация и личный кабинет с реальными данными API. CSP с nonce.
- Docker Compose: nginx, web, api, PostgreSQL 17, Redis; healthchecks, внутренние сети, постоянные volumes, production HTTPS-конфигурация.
- Ubuntu install / update / health-check / uninstall, PostgreSQL backup и план восстановления. Удаление не удаляет пользовательские volumes.
- GitHub Actions: Python 3.13 / PostgreSQL, lint, TypeScript, Next.js build, миграции, Gitleaks, Docker smoke test. Отдельный workflow публикации образов GHCR по тегам; релизов ещё нет.

Не реализованы: Admin Panel и 2FA / RBAC endpoints, Telegram Bot и Mini App, ЮKassa / Stars и чеки, VPN Node Agent и протоколы, устройства, рефералы, промокоды, уведомления, Celery и мониторинг. Подтверждение email и восстановление пароля также впереди. Каталоги этих компонентов содержат только описание следующих этапов и не запускаются как готовые сервисы.

## Проверки первого этапа

Локально (Windows / Python 3.12 / Node 24): 16 backend-тестов, Ruff lint / format, миграции upgrade → check → downgrade → upgrade и повторный seed на SQLite, TypeScript / ESLint, production Next.js build, npm audit (0 уязвимостей), синтаксис Bash. В браузере проверены регистрация → выбор тарифа → сохранение заказа → перезагрузка → выход → повторный вход.

В GitHub Actions также прошли backend-тесты на Python 3.13 / PostgreSQL 17, миграции и полный Docker Compose smoke test: сборка API и web, старт пяти контейнеров, healthchecks, чтение каталога из PostgreSQL и загрузка сайта через nginx. Установка системных пакетов на чистую Ubuntu VPS, production HTTPS и реальная VPN-связь пока не подтверждены.

## Быстрый запуск на Ubuntu

```bash
git clone https://github.com/kzolotarev95/zks95-vpn.git
cd zks95-vpn
sudo bash scripts/install.sh
```

При отсутствии `.env` установщик создаёт его со случайным паролем БД. Development доступен на VPS по http://localhost:8080; для удалённого просмотра используйте SSH-туннель. Для production сначала настройте домен и TLS, заполните `.env`, затем `sudo bash scripts/install.sh --production`. [Подробная инструкция](docs/DEPLOYMENT.md).

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

Сейчас обязательны: случайный `POSTGRES_PASSWORD`; для внешнего запуска — `DOMAIN`, `PUBLIC_URL`, `TRUSTED_HOSTS`, TLS-сертификат и `COOKIE_SECURE=true`. Поля Telegram / ЮKassa в `.env.example` зарезервированы для следующих этапов и пока не используются. Не передавайте токены в чат или Git.

- [Архитектура](docs/ARCHITECTURE.md)
- [Этапы и внешние настройки](docs/ROADMAP.md)

Секреты запрещено коммитить. Файлы `.env`, резервные копии и закрытые ключи исключены из Git.
