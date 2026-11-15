#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
# shellcheck source=/dev/null
source /etc/os-release
[[ "$ID" == ubuntu ]] || { echo "Ubuntu 22.04 or newer is required." >&2; exit 1; }
[[ "${VERSION_ID%%.*}" -ge 22 ]] || { echo "Ubuntu 22.04+ is required." >&2; exit 1; }

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl python3 openssl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<SOURCES
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
if ! command -v python3 >/dev/null || ! command -v openssl >/dev/null || ! command -v curl >/dev/null; then
  apt-get update; apt-get install -y python3 openssl curl
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  password="$(openssl rand -hex 32)"
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/" .env
  unset password
  chmod 600 .env
  if [[ "$MODE" == production ]]; then
    echo "Generated .env with a private database password. Configure HTTPS settings and rerun --production."
    exit 1
  fi
fi
python3 scripts/ensure-secrets.py
require_env
chmod 600 .env
"${COMPOSE[@]}" config --quiet

if [[ "$MODE" == production ]]; then
  # DOMAIN is expanded by the shell inside the nginx container.
  # shellcheck disable=SC2016
  "${COMPOSE[@]}" run --rm --no-deps --entrypoint sh nginx -ec \
    'test -r "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" && test -r "/etc/letsencrypt/live/$DOMAIN/privkey.pem"' || {
      echo "nginx uid 101 needs readable certificates. See docs/DEPLOYMENT.md." >&2; exit 1;
    }
fi
# Docker checks port availability on start. Preflight detects listeners before any DB changes.
python3 - "$MODE" <<'PY'
import socket, sys
from pathlib import Path
settings = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
                if '=' in line and not line.startswith('#'))
production = sys.argv[1] == 'production'
for port in ([80, 443] if production else [int(settings.get('HTTP_PORT', '8080'))]):
    with socket.socket() as sock:
        try:
            sock.bind(('0.0.0.0' if production else settings.get('BIND_ADDRESS', '127.0.0.1'), port))
        except OSError:
            raise SystemExit(f'Port {port} is busy. For an existing deployment use update.sh.')
PY

"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --wait postgres redis
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
"${COMPOSE[@]}" run --rm --no-deps api python -m app.cli seed
"${COMPOSE[@]}" up -d --wait --wait-timeout 180
printf '%s\n' "$MODE" > .deployment-mode
bash scripts/health-check.sh
"${GIT[@]}" rev-parse HEAD > .deployed-commit
echo "Installed the current development milestone. Site and account: $(sed -n 's/^PUBLIC_URL=//p' .env)"
echo "Admin: /admin. Create access: docker compose exec api python -m app.cli admin-create --email YOUR_EMAIL"
echo "Configure the Telegram bot in /admin. Billing and VPN nodes are not implemented yet."
echo "For HTTPS setup see docs/DEPLOYMENT.md."
