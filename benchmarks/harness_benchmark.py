"""Deterministic harness benchmark; it does not load or alter a model."""

import tempfile
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.harness import get_harness_profile
from core.job_store import JobStore
from core.runner import ExecutionGovernor
from memory.compactor import ContinuousCompactor
from skills.registry import Skill, SkillRegistry
from voice.assistant import NovaVoiceAssistant
import config


class _BenchmarkJobStore:
    def create_job(self, **kwargs):
        return {"job_id": "job-benchmark"}

    def update_status(self, *args, **kwargs):
        pass


def run_benchmark() -> dict:
    with tempfile.TemporaryDirectory(prefix="nova-bench-") as tmp:
        root = Path(tmp)
        registry = SkillRegistry(skills_dir=root / "skills")
        registry.register(Skill(
            name="echo",
            description="Returns value",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
            handler=lambda value: value,
        ))
        events = []
        results = [
            registry.execute("echo", {"value": "ok"}, observer=events.append),
            registry.execute("echo", {}, observer=events.append),
            registry.execute("missing", {}, observer=events.append),
        ]
        governor = ExecutionGovernor(job_store=_BenchmarkJobStore())
        with patch("core.runner.validate_workspace_path", return_value=root), \
                patch.object(governor, "_build_exec_command", side_effect=lambda cmd, _: ["/bin/sh", "-c", cmd]):
            command_result = governor.run(
                "python3 -c \"print('x' * 100000)\"",
                working_directory=str(root),
            )

        store = JobStore(root / "jobs.db")
        task_id = store.create_agent_task("benchmark task", working_directory=str(root), checkpoint=[{"role": "user", "content": "benchmark task"}])
        store.update_status(task_id, "PAUSED")
        resumed_checkpoint = JobStore(root / "jobs.db").get_agent_checkpoint(task_id)

        interrupted = [{
            "role": "assistant",
            "tool_calls": [{"id": "interrupted", "function": {"name": "write_file"}}],
        }]
        NovaVoiceAssistant._recover_interrupted_tool_calls(interrupted)

        compactor = ContinuousCompactor.__new__(ContinuousCompactor)
        seen_files = []
        compactor.compact_single_file = lambda path: seen_files.append(path)
        with patch.object(config, "COMPACTOR_ROOTS", []):
            sweep_count = compactor.run_sweep()

        checks = {
            "valid_call": results[0] == "ok" and events[0]["success"],
            "invalid_call_recoverable": results[1].startswith("Error:") and not events[1]["valid"],
            "unknown_tool_recoverable": results[2].startswith("Error:") and not events[2]["valid"],
            "profile_overlay": get_harness_profile("gemma-31b").edit_format == "str_replace",
            "trace_metadata": all("duration_ms" in event for event in events),
            "bounded_command_output": (
                command_result.success()
                and "output truncated" in command_result.stdout
                and len(command_result.stdout.encode("utf-8")) <= 33_000
            ),
            "agent_checkpoint_persists": resumed_checkpoint == [{"role": "user", "content": "benchmark task"}],
            "interrupted_tool_not_replayed": "outcome is unknown" in interrupted[-1]["content"],
            "workspace_scan_opt_in": sweep_count == 0 and not seen_files,
        }
    return {"passed": sum(checks.values()), "total": len(checks), "checks": checks}


if __name__ == "__main__":
    result = run_benchmark()
    print(f"Harness benchmark: {result['passed']}/{result['total']}")
    for name, passed in result["checks"].items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
