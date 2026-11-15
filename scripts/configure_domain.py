"""Write a production origin without evaluating .env as shell code."""

import argparse
import ipaddress
import json
import re
from pathlib import Path


def hostname(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if len(value) > 253 or "." not in value:
        raise ValueError("Укажите домен, например vpn.example.ru")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("Для сертификата нужен домен, а не IP")
    if any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in value.split(".")
    ):
        raise ValueError("Некорректное DNS-имя; используйте ASCII/punycode")
    return value


def configure(path: Path, domain: str) -> None:
    values = {
        "DOMAIN": domain,
        "PUBLIC_URL": f"https://{domain}",
        "MINIAPP_URL": f"https://{domain}/miniapp/",
        "ENVIRONMENT": "production",
        "COOKIE_SECURE": "true",
        "ENABLE_DOCS": "false",
        "TLS_DIRECTORY": "./secrets/tls",
        "TRUSTED_HOSTS": json.dumps([domain, "localhost", "127.0.0.1", "api"]),
    }
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for key, value in values.items():
        matches = [i for i, line in enumerate(lines) if line.startswith(key + "=")]
        if len(matches) > 1:
            raise ValueError(f"Duplicate {key}; resolve .env first")
        if matches:
            lines[matches[0]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
    parser.add_argument("email", nargs="?", default="")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        domain = hostname(args.domain)
        if args.email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", args.email):
            raise ValueError("Укажите email для сертификата")
        if args.check_only:
            print(domain)
        else:
            configure(Path(".env"), domain)
    except ValueError as error:
        raise SystemExit(str(error)) from None
