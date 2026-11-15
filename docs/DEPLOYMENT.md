# Установка текущего этапа

Окружение control plane: сайт, кабинет, `/admin`, API, PostgreSQL, Redis, nginx, Telegram worker и Mini App. Сайт принимает ЮKassa, бот и Mini App — Telegram Stars; перед коммерческим запуском заполните ключи провайдеров и назначьте VPN-панель тарифу. VPN-панели 3x-ui и Remnawave подключаются из админки; после подтверждённого заказа или ручной выдачи создаётся реальный клиент и сохраняется ссылка подписки. [Создание администратора, обновление с первой версии и подключение Telegram](ADMIN.md). Системная установка на чистую Ubuntu пока не проверена вручную; Docker smoke test находится в CI.

## Ubuntu 22.04 / 24.04+

Необходимы доступ root, Git, свободные порты и минимум 2 CPU / 4 GB RAM для сборки Next.js. Скрипт добавляет официальный Docker apt repository и устанавливает Docker, если он отсутствует. Он не меняет настройки firewall и не удаляет существующие данные Docker.

```bash
curl -fsSL "https://raw.githubusercontent.com/kzolotarev95/zks95-vpn/main/install-vps.sh?v=$(date +%s)" | sudo sh
```

Установщик спросит домен и необязательный email, получит сертификат Let's Encrypt, настроит HTTPS и создаст первый вход `admin/admin`. Для локальной установки из клона используйте `sudo bash scripts/install.sh`.

Если `.env` отсутствует, скрипт создаст его и сгенерирует случайный пароль PostgreSQL. Development слушает только `127.0.0.1:8080`. Для открытия на своём компьютере используйте SSH-туннель `ssh -L 8080:127.0.0.1:8080 user@vps` и адрес http://localhost:8080.

API: `/api/v1`, OpenAPI: `/api/docs`, кабинет: `/dashboard`, Mini App: `/miniapp/`. Тарифы из seed — начальные значения для разработки; это ещё не коммерческое предложение.

## HTTPS

1. Направьте A/AAAA-запись домена на VPS. Откройте TCP 80 и 443.
2. Запустите `install-vps.sh`: он запросит домен и email, получит сертификат Certbot до запуска nginx, скопирует его в закрытый каталог проекта и включит systemd-проверку продления два раза в день.
3. Сертификаты монтируются в nginx только для чтения; private key не публикуется наружу. При продлении копия заменяется атомарно и nginx получает reload.
4. Для ручного запуска из клона используйте `sudo bash scripts/setup-https.sh`; обычная development-установка остаётся на `127.0.0.1:8080`.

Production требует Docker Compose 2.24.4+ для `!override`. PostgreSQL и Redis не публикуют порты. Приватная сеть frontend использует `172.30.95.0/24`; если она занята, измените subnet, статический адрес nginx и доверенный proxy IP в API Dockerfile согласованно.

## Обновление и резервные копии

```bash
sudo bash scripts/update.sh
sudo bash scripts/health-check.sh
sudo bash infra/backup/backup.sh
sudo bash scripts/uninstall.sh
```

Update требует чистую ветку `main`, сохраняет `pg_dump -Fc` и `.env` в закрытый `backups/`, делает fast-forward, проверяет конфигурацию, собирает образы, останавливает обработчики запросов, выполняет миграции и проверяет контейнеры. Volumes не удаляются. Проверка новых полей `.env` может остановить обновление: заполните их и повторите команду. Требования новых версий следует читать перед запуском.

Копии `backups/` содержат персональные данные и секреты. Храните независимую зашифрованную копию вне VPS и регулярно проверяйте восстановление. Автоматического удаления резервных копий пока нет.

Uninstall удаляет контейнеры и сеть, сохраняя volumes, исходники и `.env`. [Восстановление](RECOVERY.md).

Удаление контейнеров одной командой:

```bash
curl -fsSL "https://raw.githubusercontent.com/kzolotarev95/zks95-vpn/main/uninstall-vps.sh?v=$(date +%s)" | sudo sh
```

Скрипт сохраняет базу и исходники; для полного удаления volumes используйте `sudo bash scripts/uninstall.sh --purge` после отдельной резервной копии.

## Проверка локальных изменений без GitHub

Из PowerShell в корне проекта соберите архив текущих файлов, включая новые файлы:

```powershell
.venv\Scripts\python.exe scripts/package-local.py
scp .\dist\zks95-vpn-local.tar.gz root@144.31.91.86:/tmp/
ssh root@144.31.91.86
```

В SSH-терминале обновите существующую установку именно в `/opt/zks95-vpn`, чтобы имя Compose-проекта и volumes сохранились:

```bash
set -e
mkdir -p /opt/zks95-vpn
tar -xzf /tmp/zks95-vpn-local.tar.gz -C /opt/zks95-vpn
cd /opt/zks95-vpn
bash scripts/apply-local.sh
bash scripts/health-check.sh
```

Архив не включает `.git`, `.env`, секреты, БД, backups и node_modules. `apply-local.sh` использует файлы на VPS, делает резервную копию работающей БД и `.env`, выполняет миграции и сохраняет существующих администраторов. Git pull/push не вызываются. Для первой настройки домена вместо `apply-local.sh` запустите `bash scripts/setup-https.sh`: A-запись домена должна указывать на `144.31.91.86`; TCP 80/443 должны быть доступны извне. Email для сертификата можно пропустить.

Новые `curl`-команды доступны по GitHub URL только после отдельной публикации этих файлов. До разрешения на push используйте локальный архив.
