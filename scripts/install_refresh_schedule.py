"""Replace the evidence-only job with the tested full dataset refresh job."""

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "io.vpnlens.dataset-refresh"
OLD_LABEL = "io.vpnlens.evidence-refresh"


def configuration(root=ROOT, python=None, interval_hours=24):
    if not 1 <= interval_hours <= 168:
        raise ValueError("Interval must be between 1 and 168 hours")
    logs = Path(root) / "data/refresh/logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            os.path.abspath(python or sys.executable),
            "-m",
            "vpnlens.refresh",
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": False,
        "StartInterval": interval_hours * 3600,
        "StandardOutPath": str(logs / "refresh.stdout.log"),
        "StandardErrorPath": str(logs / "refresh.stderr.log"),
    }


def install(
    *,
    root=ROOT,
    python=None,
    launch_agents=None,
    runner=subprocess.run,
    interval_hours=24,
):
    config = configuration(root, python, interval_hours)
    directory = Path(launch_agents or Path.home() / "Library/LaunchAgents")
    path = directory / (LABEL + ".plist")
    old_path = directory / (OLD_LABEL + ".plist")
    directory.mkdir(parents=True, exist_ok=True)
    (Path(root) / "data/refresh/logs").mkdir(parents=True, exist_ok=True)
    if path.exists():
        if plistlib.loads(path.read_bytes()) != config:
            raise RuntimeError(
                f"Existing different scheduler configuration: {path}; inspect before replacing"
            )
    else:
        with path.open("xb") as output:
            plistlib.dump(config, output)
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    old_target = f"{domain}/{OLD_LABEL}"
    already_loaded = runner(["launchctl", "print", target], capture_output=True).returncode == 0
    old_loaded = runner(["launchctl", "print", old_target], capture_output=True).returncode == 0
    started = False
    old_stopped = False
    try:
        if not already_loaded:
            runner(["launchctl", "bootstrap", domain, str(path)], check=True)
            started = True
        if old_loaded:
            runner(["launchctl", "bootout", old_target], check=True)
            old_stopped = True
        # Start only after the previous job is disabled. Existing runs are left alone.
        if not already_loaded:
            runner(["launchctl", "kickstart", target], check=True)
    except Exception:
        if started:
            runner(["launchctl", "bootout", target], capture_output=True)
        if old_stopped and old_path.exists():
            runner(["launchctl", "bootstrap", domain, str(old_path)], capture_output=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-hours", type=int, default=24)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Use the refresh CLI with your scheduler on non-macOS hosts")
    path = install(interval_hours=args.interval_hours)
    print(f"Installed {path}")
    print("Evidence-only job disabled. Daily refresh uses this checkout and Python environment.")


if __name__ == "__main__":
    main()
