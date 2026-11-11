import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from memory.compactor import ContinuousCompactor


class MemoryCompactorTests(unittest.TestCase):
    def test_sweep_is_disabled_without_opt_in_roots(self):
        compactor = ContinuousCompactor.__new__(ContinuousCompactor)
        seen = []
        compactor.compact_single_file = lambda path: seen.append(path)

        with patch.object(config, "COMPACTOR_ROOTS", []):
            self.assertEqual(compactor.run_sweep(), 0)

        self.assertEqual(seen, [])

    def test_sweep_only_reads_configured_roots(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            selected = root / "selected"
            other = root / "other"
            selected.mkdir()
            other.mkdir()
            selected_file = selected / "source.py"
            other_file = other / "source.py"
            selected_file.write_text("pass\n", encoding="utf-8")
            other_file.write_text("pass\n", encoding="utf-8")

            compactor = ContinuousCompactor.__new__(ContinuousCompactor)
            seen = []
            compactor.compact_single_file = lambda path: seen.append(path) or "summary"
            with patch.object(config, "WORKSPACE_ROOTS", [root]), \
                    patch.object(config, "COMPACTOR_ROOTS", [selected]):
                self.assertEqual(compactor.run_sweep(), 1)

            self.assertEqual(seen, [selected_file])

    def test_sweep_does_not_follow_file_symlinks_outside_selected_root(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            selected = root / "selected"
            outside = root / "outside"
            selected.mkdir()
            outside.mkdir()
            secret = outside / "secret.py"
            secret.write_text("pass\n", encoding="utf-8")
            (selected / "linked.py").symlink_to(secret)

            compactor = ContinuousCompactor.__new__(ContinuousCompactor)
            seen = []
            compactor.compact_single_file = lambda path: seen.append(path) or "summary"
            with patch.object(config, "WORKSPACE_ROOTS", [root]), \
                    patch.object(config, "COMPACTOR_ROOTS", [selected]):
                self.assertEqual(compactor.run_sweep(), 0)

            self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
