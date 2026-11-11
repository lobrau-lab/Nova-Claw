# Capability Map: Reliable Long-Running Nova

| Module | Responsibility | Depends on |
|---|---|---|
| `execution-safety` | Fix lease handling and bound command runtime/output; resolve the supported OS-level shell boundary | — |
| `long-task-continuity` | Persist task progress, checkpoint work, resume after interruption, and report incomplete work | `execution-safety` |
| `memory-privacy` | Make background file scanning opt-in and scoped to selected project roots | — |
| `completion-evidence` | Isolate tests and measure multi-step completion, recovery, and resume behavior | `long-task-continuity`, `execution-safety`, `memory-privacy` |

Build order: `execution-safety` → `long-task-continuity` → `memory-privacy` → `completion-evidence`.
