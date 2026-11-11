# Implementation Plan: Benchmaxxed Nova Harness

## Overview

Improve the existing frozen-model agent harness without changing model weights. The first slice targets the highest-confidence friction points visible in the repository: a working-tree regression that bypasses workspace safety, weak tool-call boundary validation, missing model-specific harness guidance, and traces that cannot explain tool failures.

## Scope

- Restore the hardened execution path.
- Add small model-family profile data for prompt and edit-format guidance.
- Validate tool calls before handlers run and record boundary outcomes.
- Add a deterministic benchmark covering safe tool execution, edit recovery, and traceability.

Out of scope: changing model weights, adding a new inference backend, public-benchmark scraping, or automatic prompt evolution.

## Tasks

1. Restore safe command execution and add regression coverage.
2. Add profile-driven system/tool guidance and bounded edit recovery.
3. Add tool-boundary validation and trace metadata.
4. Add a deterministic harness benchmark and run the full suite.

## Risks

- Existing local modifications are user work; edits will be limited to the harness path and tests.
- Tool schemas are JSON-like rather than backed by a validation dependency, so validation will remain intentionally small and conservative.
- The benchmark measures harness behavior, not raw model intelligence; held-out task evaluation remains a follow-up.

## Follow-up Plan: Reliable Long-Running Nova

The original Benchmaxxed Nova plan above is complete. This follow-up addresses the audit findings without changing model weights or adding runtime dependencies.

### Completed slices

1. **Execution lifecycle:** Fail closed on lease-acquisition failure; bound stdout/stderr capture; terminate the process group on timeout; do not retry timed-out commands.
2. **Task continuity:** Persist active agent checkpoints in the job database, expose `claw continue <task-id>`, recover interrupted tool calls without blindly replaying them, and compact older tool context.
3. **Privacy and test safety:** Disable background compaction scans by default, scope opt-in scans to configured roots, reject symlink escapes, isolate acceptance-test data, and mock computer-control side effects.
4. **Operations:** Generate a per-user LaunchAgent using the active Python and checkout paths without loading it automatically.

### Remaining work

- **Shell isolation decision:** The current Python CLI has no verified, supported OS-level sandbox implementation. Keep the limitation explicit until a supported mechanism or user-approved runtime is selected.
- **Completion evidence:** The deterministic harness benchmark now covers runner output bounds, task checkpoint persistence, interrupted calls, and opt-in scanning. Representative held-out coding tasks and an endurance test remain; unit tests do not establish eight-hour completion quality.

### Verification

- `python3 test_nova.py`
- `python3 -m unittest -v test_embedded_backend.py test_omlx_backend.py test_tool_contracts.py test_computer_control.py test_memory_manager.py test_job_store.py test_execution_safety.py test_memory_compactor.py test_launchd.py test_nova_cli.py`
