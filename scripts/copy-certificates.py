"""Give nginx uid/gid 101 access only to this deployment's certificate copy."""

import os
import sys
from pathlib import Path

from configure_domain import hostname


def copy(domain: str, source_root=Path("/etc/letsencrypt"), target_root=Path("secrets/tls")):
    domain = hostname(domain)
    destination = target_root / "live" / domain
    destination.mkdir(parents=True, exist_ok=True)
    for folder in (target_root, target_root / "live", destination):
        os.chown(folder, 0, 101)
        folder.chmod(0o750)
    for name in ("fullchain.pem", "privkey.pem"):
        source = source_root / "live" / domain / name
        temp = destination / (name + ".new")
        with temp.open("wb") as output:
            os.fchmod(output.fileno(), 0o640)
            os.fchown(output.fileno(), 0, 101)
            output.write(source.read_bytes())
        temp.replace(destination / name)


if __name__ == "__main__":
    copy(sys.argv[1])
