"""Bundle the current working files, including new files, without Git writes or secrets."""

import io
import subprocess
import tarfile
from pathlib import Path


def package() -> Path:
    root = Path(__file__).resolve().parent.parent
    names = (
        subprocess.run(  # noqa: S603
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    output = root / "dist" / "zks95-vpn-local.tar.gz"
    output.parent.mkdir(exist_ok=True)
    excluded = {".git", ".venv", "node_modules", ".next", "backups", "secrets", "dist"}
    with tarfile.open(output, "w:gz") as archive:
        for name in sorted(set(names) - {""}):
            path = root / name
            if not path.is_file() or path.is_symlink() or excluded.intersection(Path(name).parts):
                continue
            if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix in {
                ".sqlite3",
                ".log",
                ".pem",
                ".key",
            }:
                continue
            data = path.read_bytes()
            if b"\0" not in data:
                data = data.replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if path.suffix == ".sh" else 0o644
            archive.addfile(info, io.BytesIO(data))
    print(output)
    return output


if __name__ == "__main__":
    package()
