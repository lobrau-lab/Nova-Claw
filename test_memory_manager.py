import tempfile
import sqlite3
import unittest
from pathlib import Path

from memory.db import MemoryStore
from memory.manager import MemoryManager


class MemoryManagerTests(unittest.TestCase):
    def test_memory_connections_close_when_context_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.db")
            connection = store.get_connection()
            with connection:
                connection.execute("SELECT 1")

            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_rollover_moves_oldest_fraction_to_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MemoryManager(
                MemoryStore(Path(tmp) / "memory.db"),
                Path(tmp) / "memory.md",
                short_term_path=Path(tmp) / "short_term.json",
            )
            history = [{"role": "user", "content": str(i)} for i in range(10)]
            remaining = manager.rollover_if_needed(history, prompt_tokens=16000)
            self.assertEqual(len(remaining), 6)
            self.assertIn("0", Path(tmp, "memory.md").read_text())
            self.assertNotIn("0", " ".join(item["content"] for item in remaining))

    def test_compaction_replaces_large_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.md"
            path.write_text("old context\n" * 100, encoding="utf-8")
            manager = MemoryManager(
                MemoryStore(Path(tmp) / "memory.db"),
                path,
                short_term_path=Path(tmp) / "short_term.json",
            )
            original_limit = __import__("config").MEMORY_COMPACTION_MAX_CHARS
            __import__("config").MEMORY_COMPACTION_MAX_CHARS = 20
            try:
                self.assertTrue(manager.maybe_compact(lambda _: "compact summary"))
                self.assertIn("compact summary", path.read_text())
            finally:
                __import__("config").MEMORY_COMPACTION_MAX_CHARS = original_limit

    def test_dual_pool_auto_refresh_and_short_term_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.db")
            store.add_memory("We configured LTX-2 at 50fps", category="architecture", importance=8.0)
            manager = MemoryManager(
                store,
                Path(tmp) / "memory.md",
                short_term_path=Path(tmp) / "short_term.json",
            )
            history = [
                {"role": "user", "content": "Set up model auto-tuner"},
                {"role": "assistant", "content": "Auto-tuner active for Qwen and Gemma."},
            ]
            manager.auto_maintain_pools(
                "Set up model auto-tuner",
                "Auto-tuner active for Qwen and Gemma.",
                history,
                prompt_tokens=100,
            )
            self.assertEqual(len(manager.load_short_term_pool()), 2)
            self.assertTrue(manager.should_refresh_pools("What have we been doing earlier?", []))
            ctx = manager.build_dual_pool_context("What have we been doing earlier?", [])
            self.assertTrue(ctx["refreshed"])
            self.assertIn("Short-Term Memory Pool", ctx["formatted_context"])
            self.assertIn("Long-Term Memory Pool", ctx["formatted_context"])


if __name__ == "__main__":
    unittest.main()
