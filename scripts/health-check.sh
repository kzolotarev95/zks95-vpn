#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_env
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" exec -T api python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready',timeout=5)"
"${COMPOSE[@]}" exec -T web node -e \
  "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
"${COMPOSE[@]}" exec -T nginx wget -q -O /dev/null http://127.0.0.1:8080/health
"${COMPOSE[@]}" exec -T bot python -c \
  "import pathlib,time; assert time.time()-float(pathlib.Path('/tmp/zks95-bot-health').read_text()) < 45"
echo "PostgreSQL, Redis, API, web, nginx and bot worker checks passed."
