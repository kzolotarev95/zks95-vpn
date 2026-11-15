#!/bin/sh
set -eu
# POSIX entry point for curl | sudo sh. Persistent data is kept by default.
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
ZKS95_INSTALL_DIR=/opt/zks95-vpn
[ -f "$ZKS95_INSTALL_DIR/scripts/uninstall.sh" ] || { echo 'Installation not found.'; exit 0; }
exec bash "$ZKS95_INSTALL_DIR/scripts/uninstall.sh" "$@"
