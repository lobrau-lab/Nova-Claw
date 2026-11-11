import unittest
from pathlib import Path
from unittest.mock import patch

from core.sandbox import SandboxPolicy, SandboxUnavailableError


class SandboxPolicyTests(unittest.TestCase):
    def test_profile_denies_by_default_and_network(self):
        profile = SandboxPolicy(workdir="/tmp/nova-work").profile()
        self.assertIn("(deny default)", profile)
        self.assertNotIn("network-outbound", profile)
        self.assertIn('/tmp/nova-work', profile)

    def test_profile_allows_only_workdir_writes(self):
        profile = SandboxPolicy(workdir="/tmp/nova-work").profile()
        workdir = str(Path("/tmp/nova-work").resolve())
        self.assertIn(f'(allow file-write* (subpath "{workdir}"))', profile)
        self.assertNotIn('(allow file-write* (subpath "/Users"))', profile)

    def test_missing_native_sandbox_fails_closed(self):
        with patch("core.sandbox.sys.platform", "darwin"), patch("core.sandbox.shutil.which", return_value=None):
            with self.assertRaises(SandboxUnavailableError):
                SandboxPolicy(workdir="/tmp/nova-work").command_prefix()


if __name__ == "__main__":
    unittest.main()
