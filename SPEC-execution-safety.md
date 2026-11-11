# Spec: Execution Safety

## Implementation Status

- Implemented: failed resource leases block heavy commands; timeouts stop the process group and are not automatically retried; captured output is bounded to 32 KiB per stream; command timeouts default to 120 seconds and are capped at 1800 seconds.
- **Blocked:** OS-enforced filesystem isolation for arbitrary shell commands is not implemented. On this macOS 27.2 host, `/usr/bin/sandbox-exec` is present but its local manual marks it deprecated. Apple's App Sandbox documentation describes entitlements for app bundles, which does not directly sandbox this Python CLI. Commands still run with the user's permissions; do not treat cwd validation as isolation.
- Sources: [Apple App Sandbox](https://developer.apple.com/documentation/security/app-sandbox), [Configuring the macOS App Sandbox](https://developer.apple.com/documentation/xcode/configuring-the-macos-app-sandbox), local `man 1 sandbox-exec` (DEPRECATED), and local `man 5 launchd.plist`.

## Objective

Make Nova's local command runner fail closed when it cannot obtain required resource leases or enforce filesystem boundaries. Bound command runtime and captured output so a failed or noisy command cannot stall the agent or consume unbounded memory. This is the foundation for long-running, resumable tasks.

## Assumptions

- Nova remains a local, single-user macOS/Apple Silicon agent; model weights and inference backend do not change.
- Shell commands may read outside approved workspaces and use the network, but may write only to configured writable roots and designated temporary/cache locations.
- Changes inside an approved workspace can still be destructive; Nova's existing confirmation contract remains in force for irreversible work.
- If the OS cannot enforce a requested boundary, Nova must refuse the command rather than silently run it unrestricted. A string/regex check on shell text is not a security boundary.

## Tech Stack

- Python 3.15, macOS, standard-library `subprocess`, SQLite job history, and the existing `ResourceLease`/`ExecutionGovernor` modules.
- No new runtime dependency unless platform research proves one is necessary and the user approves it.

## Commands

- Focused tests: `python3 -m unittest -v test_execution_safety.py test_job_store.py`
- Existing focused regression suite: `python3 -m unittest -v test_embedded_backend.py test_tool_contracts.py test_computer_control.py`
- Full local suite: `python3 test_nova.py` and `python3 -m unittest -v test_embedded_backend.py test_omlx_backend.py test_tool_contracts.py test_computer_control.py test_memory_manager.py test_job_store.py test_execution_safety.py test_memory_compactor.py test_launchd.py test_nova_cli.py`
- No build or lint command is currently documented.

## Project Structure

- `core/runner.py`: command lifecycle, timeout, process-tree cleanup, bounded output, and job status.
- `core/lease.py`: resource lease result and timeout behavior.
- `core/workspace.py`: configured writable-root policy.
- `voice/assistant.py`: terminal tool contract and user-visible failure reporting.
- `test_execution_safety.py`: isolated regression tests; must not use the user's real database or workspace.

## Code Style

Keep the existing small Python modules and standard-library patterns. Check lease acquisition explicitly before spawning a process:

```python
if not lease.acquire(blocking=True):
    return blocked_result("resource lease was not acquired")
```

The example is illustrative; tests should assert observable job status and prove the command did not run.

## Testing Strategy

- Use temporary directories and an injected temporary `JobStore` for tests.
- Prove a lease timeout prevents process launch and records a non-success status.
- Still required: prove writes outside approved roots are denied by a supported OS-enforced boundary, including through child processes and symlinks; verify reads and network behavior match the stated policy.
- Prove timeout terminates the command's process tree and records a timeout, and noisy stdout/stderr remain within the documented memory/output cap with an explicit truncation marker.
- Verify existing callers and tool response formats remain compatible, except that commands previously run without enforceable isolation now fail closed.

## Boundaries

- **Always:** Check every lease result; bound captured output; persist a clear failure state; never claim a cwd check is isolation. If OS isolation becomes available, fail closed when it cannot be established.
- **Ask first:** Add dependencies, broaden writable roots, permit unrestricted shell execution, or change model/backend behavior.
- **Never:** Claim a cwd check or shell-string filter is a sandbox; run a heavy job after lease acquisition failed; silently fall back to unrestricted execution when isolation is enabled.

## Success Criteria

- No command starts when a required lease cannot be acquired.
- **Not met:** Shell writes are not yet constrained to configured writable roots at the OS boundary. A supported isolation mechanism or explicit user decision is needed.
- Timed-out commands and their descendants are stopped, and job status/output explain the timeout.
- Captured output has a fixed upper bound and signals truncation.
- Focused tests are isolated from user data and pass; existing focused regression tests remain green.

## Open Question

- Choose whether to accept deprecated `sandbox-exec` as a local-only stopgap or approve a maintained container/runtime dependency. Until then, the shell boundary remains an explicit risk; no heuristic substitution will be presented as a sandbox.
