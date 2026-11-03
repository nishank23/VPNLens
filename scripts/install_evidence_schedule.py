"""Install this checkout's daily macOS evidence refresh as a user LaunchAgent."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "io.vpnlens.evidence-refresh"


def configuration(root=ROOT, python=sys.executable):
    logs = root / "data/evidence/logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(Path(python).resolve()),
            str(root / "refresh_ip_evidence.py"),
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "StartInterval": 86400,
        "StandardOutPath": str(logs / "refresh.stdout.log"),
        "StandardErrorPath": str(logs / "refresh.stderr.log"),
    }


def main():
    if sys.platform != "darwin":
        raise RuntimeError(
            "This installer targets macOS; use the refresh CLI with your server scheduler elsewhere"
        )
    config = configuration()
    path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    path.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "data/evidence/logs").mkdir(parents=True, exist_ok=True)
    if path.exists():
        if plistlib.loads(path.read_bytes()) != config:
            raise RuntimeError(
                f"An existing different job owns {path}; inspect it before replacing"
            )
    else:
        with path.open("xb") as output:
            plistlib.dump(config, output)
    target = f"gui/{os.getuid()}/{LABEL}"
    loaded = subprocess.run(["launchctl", "print", target], capture_output=True)
    if loaded.returncode:
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
    print(f"Installed {path}")
    print("Refresh runs on job load and every 86400 seconds while this user session is available.")


if __name__ == "__main__":
    main()
