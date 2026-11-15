#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../../scripts/common.sh"
require_env
mkdir -p backups
chmod 700 backups
backup_file="backups/zks95-$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 3).dump"
trap 'rm -f -- "${backup_file}.partial"' EXIT
"${COMPOSE[@]}" exec -T postgres pg_dump -U zks95 -d zks95 -Fc > "${backup_file}.partial"
test -s "${backup_file}.partial"
mv -- "${backup_file}.partial" "$backup_file"
chmod 600 "$backup_file"
echo "Database backup: $backup_file"
