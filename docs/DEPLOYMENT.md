# Установка текущего этапа

Окружение control plane: сайт, кабинет, `/admin`, API, PostgreSQL, Redis, nginx и Telegram worker. Платежи и VPN-подключения ещё не реализованы. [Создание администратора, обновление с первой версии и подключение Telegram](ADMIN.md). Системная установка на чистую Ubuntu пока не проверена вручную; Docker smoke test находится в CI.

## Ubuntu 22.04 / 24.04+

Необходимы доступ root, Git, свободные порты и минимум 2 CPU / 4 GB RAM для сборки Next.js. Скрипт добавляет официальный Docker apt repository и устанавливает Docker, если он отсутствует. Он не меняет настройки firewall и не удаляет существующие данные Docker.

```bash
git clone https://github.com/kzolotarev95/zks95-vpn.git
cd zks95-vpn
sudo bash scripts/install.sh
```

Если `.env` отсутствует, скрипт создаст его и сгенерирует случайный пароль PostgreSQL. Development слушает только `127.0.0.1:8080`. Для открытия на своём компьютере используйте SSH-туннель `ssh -L 8080:127.0.0.1:8080 user@vps` и адрес http://localhost:8080.

API: `/api/v1`, OpenAPI: `/api/docs`, кабинет: `/dashboard`. Тарифы из seed — начальные значения для разработки; это ещё не коммерческое предложение.

## HTTPS

1. Направьте A/AAAA-записи домена на VPS. Откройте TCP 80 и 443.
2. Получите сертификат через Certbot (standalone до запуска nginx либо DNS challenge). Продление сертификата настройте отдельно с reload nginx.
3. В `.env` укажите `DOMAIN`, `PUBLIC_URL=https://ваш-домен`, `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `ENABLE_DOCS=false`, `TRUSTED_HOSTS=["ваш-домен","localhost","127.0.0.1","api"]`. `TLS_DIRECTORY` — каталог с `live/` и `archive/`, по умолчанию `/etc/letsencrypt`.
4. Nginx запускается как uid 101. Предоставьте ему только чтение нужных файлов сертификата и ключа и проход по соответствующим каталогам через ACL. Не делайте private key общедоступным. После продления сертификатов применяйте ACL повторно и выполняйте `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload`. Скрипт проверит доступность файлов до запуска.
5. `sudo bash scripts/install.sh --production`. Режим запоминается в локальном `.deployment-mode` для update / health / backup / uninstall. Для перехода с запущенного development сначала остановите его `docker compose down` (без `-v`).

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
