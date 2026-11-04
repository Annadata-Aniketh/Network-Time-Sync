"""Exercise the public launcher with isolated tools; never install host packages."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestLauncher(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="timesync launcher ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "scripts").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy2(ROOT / "timesync", self.root / "timesync")
        (self.root / "requirements.txt").write_text("example==1\n")
        self.script("bin/uname", '#!/bin/sh\necho "${TEST_OS:-Linux}"\n')
        self.script("bin/sudo", '#!/bin/sh\nexec "$@"\n')
        self.script(
            "scripts/setup_env.sh",
            """#!/bin/sh
set -eu
printf 'SETUP\\n'
if [ "${SETUP_FAIL:-0}" = 1 ]; then exit 1; fi
mkdir -p .venv/bin
printf '#!/bin/sh\\necho PYTHON "$@"\\n' > .venv/bin/python
chmod +x .venv/bin/python
cp requirements.txt .venv/.timesync-requirements
""",
        )
        self.script(
            "scripts/run_demo.sh",
            """#!/bin/sh
printf 'RUN'
for argument do printf '<%s>' "$argument"; done
printf '\\n'
""",
        )
        self.env = dict(os.environ, PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"])

    def script(self, name, content):
        path = self.root / name
        path.write_text(content)
        path.chmod(0o755)

    def run_launcher(self, *args, **environment):
        return subprocess.run(
            [str(self.root / "timesync"), *args],
            cwd="/",
            env=dict(self.env, **environment),
            capture_output=True,
            text=True,
        )

    def test_first_launch_installs_then_runs_and_later_launch_reuses_setup(self):
        first = self.run_launcher()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("SETUP", first.stdout)
        self.assertIn("RUN", first.stdout)
        second = self.run_launcher()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("SETUP", second.stdout)
        with (self.root / "requirements.txt").open("a") as stream:
            stream.write("new-package==2\n")
        self.assertIn("SETUP", self.run_launcher().stdout)

    def test_failed_setup_does_not_launch_or_write_success_marker(self):
        result = self.run_launcher(SETUP_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("RUN", result.stdout)
        self.assertFalse((self.root / ".venv/.timesync-requirements").exists())

    def test_unsupported_os_does_not_attempt_installation(self):
        result = self.run_launcher(TEST_OS="Darwin")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linux VM", result.stderr)
        self.assertNotIn("SETUP", result.stdout)

    def test_batch_arguments_reach_demo_unchanged(self):
        result = self.run_launcher(
            "--batch", "--scenario", "both", "--output-dir", "/a path/with spaces"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "RUN<--batch><--scenario><both><--output-dir></a path/with spaces>", result.stdout
        )

    def test_help_and_unknown_action_do_not_install(self):
        for argument, expected in [("--help", 0), ("unknown", 2)]:
            with self.subTest(argument=argument):
                result = self.run_launcher(argument)
                self.assertEqual(result.returncode, expected)
                self.assertNotIn("SETUP", result.stdout)

    def test_tests_without_environment_explain_how_to_set_up(self):
        result = self.run_launcher("test")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("./timesync setup", result.stderr)
