import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConfigImportTests(unittest.TestCase):
    def test_import_does_not_create_runtime_storage(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ)
            env["HOME"] = home
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONPATH"] = str(Path(__file__).parent)
            subprocess.run([sys.executable, "-c", "import config"], env=env, check=True)
            self.assertFalse((Path(home) / ".deepclaw").exists())


if __name__ == "__main__":
    unittest.main()
