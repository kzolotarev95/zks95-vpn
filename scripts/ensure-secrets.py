"""Append missing private server keys; preserve all existing settings and key material."""

import base64
import os
import secrets
from pathlib import Path


def ensure(path: Path) -> None:
    original = path.read_text(encoding="utf-8-sig")
    lines = original.splitlines()
    generated = {
        "APP_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "BOT_SERVICE_TOKEN": secrets.token_urlsafe(48),
    }
    for key, value in generated.items():
        existing = [index for index, line in enumerate(lines) if line.startswith(f"{key}=")]
        if len(existing) > 1:
            raise SystemExit(f"Duplicate {key}; resolve it without replacing existing keys.")
        if existing:
            index = existing[0]
            if not lines[index].partition("=")[2].strip():
                lines[index] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    if original != "\n".join(lines) + "\n":
        # The deployment scripts set umask 077; chmod also secures existing files.
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print("Server keys are configured; existing nonempty keys were preserved.")


if __name__ == "__main__":
    ensure(Path(".env"))
