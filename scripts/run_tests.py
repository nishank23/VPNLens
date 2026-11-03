"""Run integration tests using a dedicated DB or a temporary local PG cluster."""

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]


def run(environment):
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=environment,
    ).returncode


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if environment.get("VPNLENS_TEST_DATABASE_URL"):
        return run(environment)
    candidates = [Path(os.environ["VPNLENS_PG_BIN"])] if os.getenv("VPNLENS_PG_BIN") else []
    if shutil.which("initdb"):
        candidates.append(Path(shutil.which("initdb")).parent)
    candidates.extend(
        [
            Path("/opt/homebrew/opt/postgresql@18/bin"),
            Path("/usr/local/opt/postgresql@18/bin"),
        ]
    )
    binaries = next((folder for folder in candidates if (folder / "initdb").is_file()), None)
    if binaries is None:
        print(
            "Set VPNLENS_TEST_DATABASE_URL or VPNLENS_PG_BIN; project .env is never used.",
            file=sys.stderr,
        )
        return 2
    with tempfile.TemporaryDirectory(prefix="vpnlens-tests-") as temporary:
        folder = Path(temporary)
        data = folder / "pg"
        socket = folder / "socket"
        socket.mkdir()
        subprocess.run(
            [
                str(binaries / "initdb"),
                "-D",
                str(data),
                "-A",
                "trust",
                "--no-locale",
                "-E",
                "UTF8",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(binaries / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(folder / "postgres.log"),
                "-o",
                f"-F -k {socket} -p 55439 -c listen_addresses=''",
                "-w",
                "start",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        try:
            environment["VPNLENS_TEST_DATABASE_URL"] = make_conninfo(
                host=str(socket), port=55439, dbname="postgres", user=getpass.getuser()
            )
            return run(environment)
        finally:
            subprocess.run(
                [
                    str(binaries / "pg_ctl"),
                    "-D",
                    str(data),
                    "-m",
                    "immediate",
                    "-w",
                    "stop",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    raise SystemExit(main())
