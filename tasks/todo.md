# Benchmaxxed Nova Harness

- [x] Restore safe command execution and regression coverage
- [x] Add model-family profile and edit guidance
- [x] Add tool-boundary validation and trace metadata
- [x] Add deterministic benchmark and verify the full suite

## Reliable Long-Running Nova Follow-up

- [x] Fix lease failure handling; bound command output; kill child processes on timeout; avoid retrying partial timed-out commands.
- [x] Persist and resume paused/interrupted agent task checkpoints; report step-limit stops with a task ID.
- [x] Make file compaction opt-in and reject symlink escapes.
- [x] Isolate acceptance tests from user databases, skills, workspaces, and computer-control side effects.
- [x] Generate a valid per-user LaunchAgent plist from the active checkout and Python environment.
- [x] Extend the deterministic benchmark to cover command output, task checkpoints, interrupted calls, and compaction opt-in.
- [ ] Select a supported OS-level shell isolation strategy; current shell commands remain unsandboxed.
- [ ] Run held-out multi-step coding tasks and an endurance evaluation.
