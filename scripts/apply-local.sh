#!/usr/bin/env bash
set -Eeuo pipefail
# Deploy the files currently on disk. No fetch, pull, checkout or push.
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  exec bash scripts/install.sh "$@"
fi
if [[ ! -f .env ]]; then exec bash scripts/install.sh "$@"; fi
python3 scripts/ensure-secrets.py
require_env
"${COMPOSE[@]}" config --quiet
if [[ -n "$("${COMPOSE[@]}" ps --status running -q postgres)" ]]; then
  bash infra/backup/backup.sh
fi
mkdir -p backups
cp .env "backups/env-before-local-$(date -u +%Y%m%dT%H%M%SZ).private"
chmod 600 backups/*.private
"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --wait postgres redis
"${COMPOSE[@]}" stop nginx web miniapp api bot
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
"${COMPOSE[@]}" run --rm --no-deps api python -m app.cli seed
"${COMPOSE[@]}" run --rm --no-deps api python -m app.cli admin-bootstrap
"${COMPOSE[@]}" up -d --wait --wait-timeout 180
printf '%s\n' "$MODE" > .deployment-mode
bash scripts/health-check.sh
echo 'Local files deployed. Database volumes and existing accounts were preserved.'
