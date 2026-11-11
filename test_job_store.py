import tempfile
import sqlite3
import unittest
from pathlib import Path

from core.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def test_connections_close_when_context_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            connection = store._get_conn()
            with connection:
                connection.execute("SELECT 1")

            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_agent_checkpoint_survives_store_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "jobs.db"
            store = JobStore(db_path)
            task_id = store.create_agent_task("Build a game", working_directory=tmp)
            checkpoint = [{"role": "user", "content": "Build a game"}]

            store.save_agent_checkpoint(task_id, checkpoint)
            store.update_status(task_id, "PAUSED")
            reopened = JobStore(db_path)
            task = reopened.get_job(task_id)

            self.assertEqual(task["status"], "PAUSED")
            self.assertEqual(reopened.get_agent_checkpoint(task_id), checkpoint)

    def test_clearing_checkpoint_does_not_remove_task_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            task_id = store.create_agent_task("Build a game", working_directory=tmp)
            store.save_agent_checkpoint(task_id, [{"role": "user", "content": "Build a game"}])

            store.clear_agent_checkpoint(task_id)

            self.assertIsNone(store.get_agent_checkpoint(task_id))
            self.assertEqual(store.get_job(task_id)["command"], "Build a game")

    def test_checkpoint_write_fails_without_overwriting_corrupt_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            task_id = store.create_agent_task("Build a game", working_directory=tmp)
            with store._get_conn() as conn:
                conn.execute("UPDATE jobs SET metadata_json = ? WHERE job_id = ?", ("invalid-json", task_id))

            with self.assertRaises(ValueError):
                store.save_agent_checkpoint(task_id, [])

            with store._get_conn() as conn:
                value = conn.execute("SELECT metadata_json FROM jobs WHERE job_id = ?", (task_id,)).fetchone()[0]
            self.assertEqual(value, "invalid-json")

    def test_agent_task_can_be_discarded_but_active_task_cannot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            task_id = store.create_agent_task("Build a game", working_directory=tmp)

            self.assertFalse(store.delete_agent_task(task_id))
            store.update_status(task_id, "PAUSED")
            self.assertTrue(store.delete_agent_task(task_id))
            self.assertIsNone(store.get_job(task_id))


if __name__ == "__main__":
    unittest.main()
