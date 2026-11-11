import os
import shlex
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runner import ExecutionGovernor


class FakeJobStore:
    def __init__(self):
        self.status_updates = []

    def create_job(self, **kwargs):
        return {"job_id": "job-test"}

    def update_status(self, job_id, status, **kwargs):
        self.status_updates.append((status, kwargs))


class ExecutionSafetyTests(unittest.TestCase):
    def run_isolated_command(self, command, timeout=5.0):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        store = FakeJobStore()
        governor = ExecutionGovernor(job_store=store)
        with patch("core.runner.validate_workspace_path", return_value=Path(temp_dir.name)), \
                patch.object(governor, "_build_exec_command", side_effect=lambda cmd, _: ["/bin/sh", "-c", cmd]):
            result = governor.run(command, working_directory=temp_dir.name, timeout=timeout)
        return result, Path(temp_dir.name)

    def test_command_timeout_must_be_within_supported_bounds(self):
        governor = ExecutionGovernor(job_store=FakeJobStore())
        with self.assertRaises(ValueError):
            governor.run("echo never", timeout=0)
        with self.assertRaises(ValueError):
            governor.run("echo never", timeout=1801)

    def assert_process_stopped(self, pid):
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if not state or state.startswith("Z"):
                return
            time.sleep(0.05)
        self.fail(f"process {pid} is still running")

    def test_heavy_command_does_not_run_without_resource_lease(self):
        class UnavailableLease:
            def __init__(self, **kwargs):
                pass

            def acquire(self, blocking=True):
                return False

            def release(self):
                pass

        store = FakeJobStore()
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch("core.runner.validate_workspace_path", return_value=Path(temp_dir)), \
                patch("core.runner.ResourceLease", UnavailableLease), \
                patch("core.runner.subprocess.Popen") as popen:
            result = ExecutionGovernor(job_store=store).run(
                "echo should-not-run",
                working_directory=temp_dir,
                resource_class="heavy",
            )

        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.failure_class, "GPU_CONTENTION")
        self.assertEqual(store.status_updates[-1][0], "BLOCKED")
        popen.assert_not_called()

    def test_destructive_command_is_blocked_before_spawn(self):
        store = FakeJobStore()
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch("core.runner.validate_workspace_path", return_value=Path(temp_dir)), \
                patch("core.runner.subprocess.Popen") as popen, \
                patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVA_ALLOW_DESTRUCTIVE_COMMANDS", None)
            result = ExecutionGovernor(job_store=store).run(
                "rm -rf build",
                working_directory=temp_dir,
            )

        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.failure_class, "COMMAND_APPROVAL_REQUIRED")
        popen.assert_not_called()

    def test_noisy_command_output_is_bounded_and_marked(self):
        result, _ = self.run_isolated_command("python3 -c \"print('x' * 100000)\"")

        self.assertTrue(result.success())
        self.assertIn("output truncated", result.stdout)
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 33_000)

    def test_timeout_kills_command_and_its_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            script = (
                "import subprocess; "
                "p=subprocess.Popen(['python3','-c','import time; time.sleep(2)']); "
                f"open({str(pid_file)!r},'w').write(str(p.pid)); p.wait()"
            )
            started = time.monotonic()
            result, _ = self.run_isolated_command(f"python3 -c {shlex.quote(script)}", timeout=0.3)
            elapsed = time.monotonic() - started

            self.assertEqual(result.exit_code, 124)
            self.assertEqual(result.status, "FAILED")
            self.assertLess(elapsed, 1.5)
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            self.assert_process_stopped(child_pid)

    def test_command_that_leaves_a_background_child_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            script = (
                "import subprocess; "
                "p=subprocess.Popen(['python3','-c','import time; time.sleep(30)']); "
                f"open({str(pid_file)!r},'w').write(str(p.pid))"
            )
            started = time.monotonic()
            result, _ = self.run_isolated_command(f"python3 -c {shlex.quote(script)}", timeout=0.3)

            self.assertEqual(result.exit_code, 124)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assert_process_stopped(int(pid_file.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
