import tempfile
import unittest
import plistlib
from pathlib import Path

from scripts.install_launchd import LABEL, build_agent_plist, write_agent_plist


class LaunchdTests(unittest.TestCase):
    def test_generated_agent_uses_absolute_checkout_and_python_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = build_agent_plist(root / "python", root / "project", root / "logs")

            self.assertEqual(result["Label"], LABEL)
            resolved_root = root.resolve()
            self.assertEqual(result["ProgramArguments"], [str(resolved_root / "python"), str(resolved_root / "project" / "nova.py"), "live"])
            self.assertEqual(result["WorkingDirectory"], str(resolved_root / "project"))
            self.assertTrue(result["KeepAlive"])

    def test_writer_creates_private_per_user_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "LaunchAgents" / f"{LABEL}.plist"
            written = write_agent_plist(
                output,
                Path("/usr/bin/python3"),
                Path(tmp),
                log_dir=Path(tmp) / "logs",
            )

            self.assertEqual(written, output)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with output.open("rb") as stream:
                self.assertEqual(plistlib.load(stream)["Label"], LABEL)


if __name__ == "__main__":
    unittest.main()
