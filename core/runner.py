#!/usr/bin/env python3
"""
DeepClaw Nova - Invariant-Driven Execution Governor
Executes commands with workspace path validation, macOS taskpolicy QoS scheduling,
atomic lease governance, and deterministic self-healing loops.
"""

import os
import signal
import sys
import threading
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import config
from core.lease import ResourceLease, ResourceLeaseError
from core.classifier import classify_failure, CLASS_WORKSPACE_VIOLATION
from core.repair import select_repair_strategy
from core.workspace import validate_workspace_path, WorkspaceViolationError
from core.job_store import JobStore
from core.sandbox import SandboxPolicy, SandboxUnavailableError, sandbox_required

_MAX_CAPTURE_BYTES = int(32 * 1024 * getattr(config, "STRICTNESS_FACTOR", 0.95))


def _start_output_capture(stream):
    capture = {"data": bytearray(), "truncated": False}

    def drain():
        while chunk := stream.read(8192):
            capture["data"].extend(chunk)
            if len(capture["data"]) > _MAX_CAPTURE_BYTES:
                del capture["data"][:-_MAX_CAPTURE_BYTES]
                capture["truncated"] = True

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    return capture, thread


def _captured_text(capture):
    text = bytes(capture["data"]).decode("utf-8", errors="replace")
    if capture["truncated"]:
        return f"{text}\n[output truncated; showing last {_MAX_CAPTURE_BYTES} bytes]"
    return text


def _kill_process_tree(proc):
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            pass
        except OSError:
            pass
    proc.kill()


class ExecutionResult:
    def __init__(
        self,
        job_id: str,
        status: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        retries_used: int = 0,
        failure_class: Optional[str] = None,
        duration: float = 0.0,
    ):
        self.job_id = job_id
        self.status = status
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.retries_used = retries_used
        self.failure_class = failure_class
        self.duration = duration

    def success(self) -> bool:
        return self.status == "COMPLETE" and self.exit_code == 0

class ExecutionGovernor:
    def __init__(self, job_store: Optional[JobStore] = None):
        self.store = job_store or JobStore()

    def run(
        self,
        command: str,
        working_directory: Optional[str] = None,
        resource_class: str = "general",
        timeout: float = config.DEFAULT_COMMAND_TIMEOUT_SECONDS,
        env: Optional[Dict[str, str]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> ExecutionResult:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= config.MAX_COMMAND_TIMEOUT_SECONDS:
            raise ValueError(f"timeout must be between 1 and {config.MAX_COMMAND_TIMEOUT_SECONDS} seconds.")
        cwd = Path(working_directory or os.getcwd())
        start_time = time.time()
        created = self.store.create_job(command=command, resource_class=resource_class, working_directory=str(cwd))
        job_id = created["job_id"]

        # Step 1: Validate Workspace Boundary
        try:
            cwd = validate_workspace_path(cwd)
        except WorkspaceViolationError as wve:
            self.store.update_status(job_id, "BLOCKED", failure_class=CLASS_WORKSPACE_VIOLATION)
            return ExecutionResult(
                job_id=job_id,
                status="BLOCKED",
                exit_code=1,
                stdout="",
                stderr=str(wve),
                failure_class=CLASS_WORKSPACE_VIOLATION,
                duration=time.time() - start_time,
            )

        # Step 2: Retry Loop with Surgical Self-Healing
        retry_count = 0
        last_failure_class = None
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)

        while True:
            if cancel_event and cancel_event.is_set():
                self.store.update_status(job_id, "CANCELED")
                return ExecutionResult(job_id, "CANCELED", 130, "", "Command canceled.", duration=time.time() - start_time)
            # Acquire Resource Lease if heavy
            lease = None
            if resource_class in ("heavy", "metal", "training", "diffusion"):
                lease = ResourceLease(resource_name="metal_compute", owner=f"nova-{job_id}", timeout=15.0)
                try:
                    if not lease.acquire(blocking=True):
                        raise ResourceLeaseError("Timed out waiting for the Metal resource lease.")
                except ResourceLeaseError as rle:
                    self.store.update_status(job_id, "BLOCKED", failure_class="GPU_CONTENTION")
                    return ExecutionResult(
                        job_id=job_id,
                        status="BLOCKED",
                        exit_code=1,
                        stdout="",
                        stderr=str(rle),
                        failure_class="GPU_CONTENTION",
                        duration=time.time() - start_time,
                    )

            self.store.update_status(job_id, "RUNNING")
            # Build command execution list (macOS QoS taskpolicy wrapper)
            try:
                self._sandbox_workdir = cwd
                try:
                    cmd_args = self._build_exec_command(command, resource_class)
                finally:
                    del self._sandbox_workdir
            except SandboxUnavailableError as exc:
                self.store.update_status(job_id, "BLOCKED", failure_class="SANDBOX_UNAVAILABLE")
                return ExecutionResult(job_id, "BLOCKED", 1, "", str(exc), duration=time.time() - start_time)

            exit_code = 0
            stdout = ""
            stderr = ""
            proc = None
            output_threads = []
            try:
                proc = subprocess.Popen(
                    cmd_args,
                    cwd=str(cwd),
                    env=merged_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=(os.name == "posix"),
                    bufsize=0,
                )
                stdout_capture, stdout_thread = _start_output_capture(proc.stdout)
                stderr_capture, stderr_thread = _start_output_capture(proc.stderr)
                output_threads = [stdout_thread, stderr_thread]
                deadline = time.monotonic() + timeout
                timed_out = False
                try:
                    while proc.poll() is None:
                        if cancel_event and cancel_event.is_set():
                            _kill_process_tree(proc)
                            proc.wait()
                            exit_code = 130
                            break
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(cmd_args, timeout)
                        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                    else:
                        exit_code = proc.returncode
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _kill_process_tree(proc)
                    proc.wait()
                    exit_code = 124
                for thread in output_threads:
                    thread.join(timeout=max(0.0, deadline - time.monotonic()))
                if any(thread.is_alive() for thread in output_threads):
                    timed_out = True
                    _kill_process_tree(proc)
                    for thread in output_threads:
                        thread.join(timeout=1.0)
                    exit_code = 124
                canceled = bool(cancel_event and cancel_event.is_set() and exit_code == 130)
                if canceled:
                    stderr += "\nProcess canceled."
                elif timed_out:
                    stderr += f"\nProcess timed out after {timeout} seconds."
                stdout = _captured_text(stdout_capture)
                stderr = _captured_text(stderr_capture) + stderr
            except Exception as e:
                if proc is not None and proc.poll() is None:
                    _kill_process_tree(proc)
                    proc.wait()
                for thread in output_threads:
                    thread.join()
                exit_code = 1
                stderr = str(e)
            finally:
                if proc is not None:
                    if proc.stdout:
                        proc.stdout.close()
                    if proc.stderr:
                        proc.stderr.close()
                if lease:
                    lease.release()

            # Step 3: Validate Outcome
            if cancel_event and cancel_event.is_set():
                self.store.update_status(job_id, "CANCELED")
                return ExecutionResult(job_id, "CANCELED", 130, stdout, stderr, duration=time.time() - start_time)
            if exit_code == 0:
                self.store.update_status(job_id, "COMPLETE")
                return ExecutionResult(
                    job_id=job_id,
                    status="COMPLETE",
                    exit_code=0,
                    stdout=stdout,
                    stderr=stderr,
                    retries_used=retry_count,
                    duration=time.time() - start_time,
                )

            # Step 4: Classify Failure & Execute Bounded Repair
            last_failure_class = classify_failure(exit_code=exit_code, stderr=stderr, stdout=stdout)
            repair_strategy = select_repair_strategy(last_failure_class, retry_count)

            if repair_strategy.can_retry and retry_count < 2:
                retry_count += 1
                self.store.update_status(job_id, "RECOVERING", failure_class=last_failure_class, repair_action=repair_strategy.name, increment_retry=True)
                repair_strategy.execute({"job_id": job_id, "stderr": stderr, "stdout": stdout})
                continue
            else:
                final_st = "BLOCKED" if retry_count >= 2 else "FAILED"
                self.store.update_status(job_id, final_st, failure_class=last_failure_class, repair_action=repair_strategy.name)
                return ExecutionResult(
                    job_id=job_id,
                    status=final_st,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    retries_used=retry_count,
                    failure_class=last_failure_class,
                    duration=time.time() - start_time,
                )

    def _build_exec_command(self, command: str, resource_class: str) -> list:
        prefix = []
        if sandbox_required():
            prefix = SandboxPolicy(getattr(self, "_sandbox_workdir", Path.cwd()), read_roots=(config.MODELS_DIR,)).command_prefix()
        if sys.platform == "darwin":
            # Use taskpolicy on macOS for QoS enforcement
            if resource_class in ("background", "compactor"):
                return prefix + ["taskpolicy", "-b", "bash", "-c", command]
            else:
                return prefix + ["taskpolicy", "-c", "utility", "bash", "-c", command]
        return prefix + ["bash", "-c", command]
