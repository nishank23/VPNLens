"""Scheduler replacement ordering without changing the real launchd state."""

import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.install_refresh_schedule import LABEL, OLD_LABEL, configuration, install


class SchedulerTests(unittest.TestCase):
    def test_venv_path_is_preserved_and_no_credentials_embedded(self):
        config = configuration(Path("/tmp/project"), "/tmp/project/.venv/bin/python")
        self.assertEqual(config["ProgramArguments"][0], "/tmp/project/.venv/bin/python")
        self.assertFalse(config["RunAtLoad"])
        self.assertNotIn("EnvironmentVariables", config)
        self.assertEqual(config["StartInterval"], 86400)

    def test_new_job_loaded_before_old_job_stopped_and_started_after(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            loaded = args[1] == "print" and args[2].endswith("/" + OLD_LABEL)
            return subprocess.CompletedProcess(args, 0 if loaded or args[1] != "print" else 1)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            agents = root / "agents"
            install(root=root, python="/tmp/python", launch_agents=agents, runner=runner)
            actions = [args[1] for args in calls]
            self.assertLess(actions.index("bootstrap"), actions.index("bootout"))
            self.assertLess(actions.index("bootout"), actions.index("kickstart"))
            saved = plistlib.loads((agents / (LABEL + ".plist")).read_bytes())
            self.assertEqual(saved["WorkingDirectory"], str(root))

    def test_failed_new_bootstrap_does_not_disable_old_job(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if args[1] == "bootstrap":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0 if args[2].endswith("/" + OLD_LABEL) else 1)

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(subprocess.CalledProcessError):
                install(
                    root=Path(folder),
                    launch_agents=Path(folder) / "agents",
                    runner=runner,
                )
        self.assertNotIn("bootout", [args[1] for args in calls])

    def test_existing_different_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / (LABEL + ".plist")
            original = plistlib.dumps({"Label": "other"})
            path.write_bytes(original)
            with self.assertRaises(RuntimeError):
                install(root=root, launch_agents=root)
            self.assertEqual(path.read_bytes(), original)

    def test_failed_start_restores_previous_job(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if args[1] == "print":
                return subprocess.CompletedProcess(
                    args, 0 if args[2].endswith("/" + OLD_LABEL) else 1
                )
            if args[1] == "kickstart":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            agents = root / "agents"
            agents.mkdir()
            old = agents / (OLD_LABEL + ".plist")
            old.write_bytes(plistlib.dumps({"Label": OLD_LABEL}))
            with self.assertRaises(subprocess.CalledProcessError):
                install(root=root, launch_agents=agents, runner=runner)
            self.assertEqual(
                calls[-1],
                [
                    "launchctl",
                    "bootstrap",
                    f"gui/{__import__('os').getuid()}",
                    str(old),
                ],
            )
            self.assertEqual(old.read_bytes(), plistlib.dumps({"Label": OLD_LABEL}))
