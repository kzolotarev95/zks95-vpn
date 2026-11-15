#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
require_env
[[ -z "$("${GIT[@]}" status --porcelain --untracked-files=normal)" ]] || {
  echo "Working tree has local changes. Commit or preserve them before updating." >&2; exit 1;
}
[[ "$("${GIT[@]}" branch --show-current)" == main ]] || { echo "Check out main first." >&2; exit 1; }
previous="$(cat .deployed-commit 2>/dev/null || "${GIT[@]}" rev-parse HEAD)"
echo "Current commit: $previous"
"${GIT[@]}" fetch origin main
"${GIT[@]}" merge-base --is-ancestor HEAD origin/main || {
  echo "main diverged. Resolve the history before updating." >&2; exit 1;
}
if [[ -f .deployed-commit && "$previous" == "$("${GIT[@]}" rev-parse origin/main)" ]]; then
  bash scripts/health-check.sh
  echo "Already current."
  exit 0
fi
bash infra/backup/backup.sh
mkdir -p backups
cp .env "backups/env-$(date -u +%Y%m%dT%H%M%SZ).private"
chmod 600 backups/*.private

on_error() {
  echo "Update failed. Database volumes were preserved. Previous commit: $previous" >&2
  echo "Use docs/RECOVERY.md; do not downgrade the DB or delete volumes automatically." >&2
}
trap on_error ERR
"${GIT[@]}" merge --ff-only origin/main
python3 scripts/ensure-secrets.py
require_env
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build --pull
# Stop request handlers before schema changes; postgres and redis remain running.
"${COMPOSE[@]}" stop nginx web api
"${COMPOSE[@]}" stop bot
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
"${COMPOSE[@]}" run --rm --no-deps api python -m app.cli admin-bootstrap
"${COMPOSE[@]}" up -d --wait --wait-timeout 180
bash scripts/health-check.sh
"${GIT[@]}" rev-parse HEAD > .deployed-commit
echo "Updated successfully: $previous -> $("${GIT[@]}" rev-parse HEAD)"
