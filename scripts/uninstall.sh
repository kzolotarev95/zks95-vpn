#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
"${COMPOSE[@]}" down --remove-orphans
echo "Containers and networks removed. Database/Redis volumes, .env, code and backups preserved."
