# Fixed repository commands and temporary test paths; no external command input.
# ruff: noqa: S603
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_upgrade_preserves_legacy_users_and_sessions(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}

    def migrate(target):
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target],
            env=environment,
            check=True,
            capture_output=True,
        )

    migrate("0001")
    user_id = "a" * 32
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
            (user_id, "legacy@example.com", "old-hash", 1, "2026-11-15 00:00:00"),
        )
        db.execute(
            "INSERT INTO user_sessions VALUES (?, ?, ?, ?, ?)",
            ("b" * 32, user_id, "c" * 64, "2026-12-15 00:00:00", "2026-11-15 00:00:00"),
        )
    migrate("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT email,password_hash FROM users").fetchone() == (
            "legacy@example.com",
            "old-hash",
        )
        assert db.execute("SELECT purpose,token_hash FROM user_sessions").fetchone() == (
            "user",
            "c" * 64,
        )


def test_secret_upgrade_does_not_rotate_existing_keys(tmp_path):
    path = tmp_path / ".env"
    path.write_text("POSTGRES_PASSWORD=" + "d" * 64 + "\n")
    script = str(Path("scripts/ensure-secrets.py").resolve())
    subprocess.run([sys.executable, script], cwd=tmp_path, check=True, capture_output=True)
    first = path.read_text()
    subprocess.run([sys.executable, script], cwd=tmp_path, check=True, capture_output=True)
    assert path.read_text() == first
    assert "APP_ENCRYPTION_KEY=" in first
    assert "BOT_SERVICE_TOKEN=" in first
