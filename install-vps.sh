#!/bin/sh
set -eu
# POSIX entry point: works when piped to sudo sh. Interactive input uses /dev/tty.
ZKS95_INSTALL_DIR=/opt/zks95-vpn
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
# shellcheck disable=SC1091
. /etc/os-release
[ "$ID" = ubuntu ] && [ "${VERSION_ID%%.*}" -ge 22 ] || {
  echo 'Ubuntu 22.04+ is required.' >&2; exit 1;
}
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 openssl
if [ -d "$ZKS95_INSTALL_DIR/.git" ]; then
  [ -z "$(git -c "safe.directory=$ZKS95_INSTALL_DIR" -C "$ZKS95_INSTALL_DIR" status --porcelain)" ] || {
    echo 'Local changes exist. Run sudo bash scripts/setup-https.sh from the checkout.' >&2; exit 1;
  }
  git -c "safe.directory=$ZKS95_INSTALL_DIR" -C "$ZKS95_INSTALL_DIR" pull --ff-only
else
  git clone --branch main https://github.com/kzolotarev95/zks95-vpn.git "$ZKS95_INSTALL_DIR"
fi
exec bash "$ZKS95_INSTALL_DIR/scripts/setup-https.sh"
