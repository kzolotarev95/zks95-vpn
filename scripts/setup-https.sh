#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_root
[[ "$ROOT" == /opt/zks95-vpn ]] || { echo 'Production path must be /opt/zks95-vpn.' >&2; exit 1; }
# shellcheck source=/dev/null
source /etc/os-release
[[ "$ID" == ubuntu && "${VERSION_ID%%.*}" -ge 22 ]] || { echo 'Ubuntu 22.04+ required.' >&2; exit 1; }
read -r -p 'Домен (A-запись должна указывать на IP вашей VPS): ' domain </dev/tty
certificate_email="${ZKS95_CERTIFICATE_EMAIL:-}"
if [[ -z "$certificate_email" ]]; then
  read -r -p 'Email для уведомлений о сертификате (Enter, чтобы пропустить): ' certificate_email </dev/tty
fi
domain="$(python3 scripts/configure_domain.py "$domain" "$certificate_email" --check-only)"
registration=(--register-unsafely-without-email)
if [[ -n "$certificate_email" ]]; then registration=(--email "$certificate_email"); fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y certbot
if [[ -f .env ]]; then
  if command -v docker >/dev/null && [[ -n "$("${COMPOSE[@]}" ps --status running -q postgres)" ]]; then
    bash infra/backup/backup.sh
  fi
  mkdir -p backups
  cp .env "backups/env-before-https-$(date -u +%Y%m%dT%H%M%SZ).private"
  chmod 600 backups/*.private
else
  cp .env.example .env
  password="$(openssl rand -hex 32)"
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/" .env
  unset password
fi
python3 scripts/ensure-secrets.py

# Standalone is used only for initial issuance; future renewals use webroot.
was_running=false
if command -v docker >/dev/null && [[ -f .deployment-mode ]]; then
  if [[ -n "$("${COMPOSE[@]}" ps --status running -q nginx)" ]]; then
    was_running=true
    "${COMPOSE[@]}" stop nginx
  fi
fi
restart_previous() {
  if [[ "$was_running" == true ]]; then "${COMPOSE[@]}" start nginx || true; fi
}
trap restart_previous ERR
certbot certonly --standalone --non-interactive --agree-tos "${registration[@]}" \
  --cert-name "$domain" --keep-until-expiring -d "$domain"
restart_previous
trap - ERR

python3 scripts/configure_domain.py "$domain" "$certificate_email"
python3 scripts/copy-certificates.py "$domain"
mkdir -p secrets/acme/.well-known/acme-challenge
chmod 755 secrets/acme secrets/acme/.well-known secrets/acme/.well-known/acme-challenge
ZKS95_DEPLOYMENT_MODE=production bash scripts/apply-local.sh

install -m 644 infra/systemd/zks95-certificate.service /etc/systemd/system/zks95-certificate.service
install -m 644 infra/systemd/zks95-certificate.timer /etc/systemd/system/zks95-certificate.timer
systemctl daemon-reload
systemctl enable --now zks95-certificate.timer
echo "Сайт: https://$domain · админ-панель: https://$domain/admin"
echo 'При первой установке: admin / admin. Существующий администратор сохранён.'
