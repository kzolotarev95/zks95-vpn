#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
if [[ "${1:-}" == --purge ]]; then
  read -r -p 'Delete this deployment database and Redis volumes? Type DELETE: ' confirmation </dev/tty
  [[ "$confirmation" == DELETE ]] || { echo 'Cancelled.'; exit 1; }
  if command -v systemctl >/dev/null; then
    systemctl disable --now zks95-certificate.timer 2>/dev/null || true
  fi
  "${COMPOSE[@]}" down --remove-orphans --volumes
  echo 'Containers, networks and database/Redis volumes deleted. Code, .env and backups preserved.'
  exit 0
fi
if command -v systemctl >/dev/null; then
  systemctl disable --now zks95-certificate.timer 2>/dev/null || true
fi
"${COMPOSE[@]}" down --remove-orphans
echo "Containers and networks removed. Database/Redis volumes, .env, code and backups preserved."
