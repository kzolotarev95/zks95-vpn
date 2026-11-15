"""Validate deployment settings without evaluating or printing secrets."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def validate(path: Path, production: bool) -> list[str]:
    config: dict[str, str] = {}
    errors = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key.strip() in config:
            errors.append("Invalid or duplicate .env setting")
            continue
        config[key.strip()] = value.strip()
    if not re.fullmatch(r"[a-fA-F0-9]{64}", config.get("POSTGRES_PASSWORD", "")):
        errors.append("POSTGRES_PASSWORD must be 64 random hex characters")
    url = urlsplit(config.get("PUBLIC_URL", ""))
    if url.scheme not in {"http", "https"} or not url.hostname or url.path not in {"", "/"}:
        errors.append("PUBLIC_URL must be an http(s) origin without a path")
    if url.username or url.password or url.query or url.fragment:
        errors.append("PUBLIC_URL must not contain credentials, a query or fragment")
    try:
        hosts = json.loads(config.get("TRUSTED_HOSTS", "[]"))
        if not isinstance(hosts, list) or any(not isinstance(item, str) for item in hosts):
            raise ValueError
        if url.hostname not in hosts or "localhost" not in hosts or "api" not in hosts:
            errors.append("TRUSTED_HOSTS must include PUBLIC_URL hostname, localhost and api")
        if "*" in hosts:
            errors.append("Wildcard TRUSTED_HOSTS is not allowed")
    except (ValueError, TypeError):
        errors.append("TRUSTED_HOSTS must be a JSON array")
    if production:
        domain = config.get("DOMAIN", "")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
            errors.append("DOMAIN must be a DNS hostname")
        if not domain or domain.endswith(".example.com") or domain != url.hostname:
            errors.append("DOMAIN must be your real PUBLIC_URL hostname")
        if url.scheme != "https" or config.get("COOKIE_SECURE") != "true":
            errors.append("Production requires HTTPS and COOKIE_SECURE=true")
        if config.get("ENVIRONMENT") != "production":
            errors.append("Set ENVIRONMENT=production")
    elif config.get("ENVIRONMENT") == "production":
        errors.append("Use --production when ENVIRONMENT=production")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    try:
        issues = validate(Path(".env"), args.production)
    except (OSError, ValueError):
        issues = ["Cannot parse .env configuration"]
    for issue in issues:
        print(f"Configuration error: {issue}")
    raise SystemExit(bool(issues))
