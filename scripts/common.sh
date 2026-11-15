#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${ZKS95_DEPLOYMENT_MODE:-$(cat .deployment-mode 2>/dev/null || printf development)}"
if [[ "${1:-}" == "--production" ]]; then MODE=production; fi
COMPOSE=(docker compose -f docker-compose.yml)
GIT=(git -c "safe.directory=$ROOT")
if [[ "$MODE" == production ]]; then COMPOSE+=(-f docker-compose.prod.yml); fi
umask 077

require_root() {
  if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
}

require_env() {
  if [[ ! -f .env ]]; then echo "Missing .env. Run install.sh first." >&2; exit 1; fi
  local arguments=()
  if [[ "$MODE" == production ]]; then arguments+=(--production); fi
  python3 scripts/validate-env.py "${arguments[@]}"
}
