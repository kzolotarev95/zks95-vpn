#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
domain="$(python3 -c 'from pathlib import Path; print(next(line.split("=",1)[1] for line in Path(".env").read_text().splitlines() if line.startswith("DOMAIN=")))')"
certbot renew --cert-name "$domain" --webroot -w "$ROOT/secrets/acme" --quiet
python3 scripts/copy-certificates.py "$domain"
"${COMPOSE[@]}" exec -T nginx nginx -s reload
