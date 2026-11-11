# DeepClaw Nova installation

## Embedded MLX runtime

Use the Python environment that will run Nova:

```bash
sh scripts/install_embedded.sh /path/to/python
```

For the existing local environment:

```bash
sh scripts/install_embedded.sh ./venv/bin/python
```

The installer intentionally passes `--no-deps`. `mlx-vlm` currently declares
optional server/UI/audio dependencies, including `sentencepiece`; Python 3.15
has no compatible `sentencepiece` wheel on this host, and pip otherwise tries
to build it with CMake. Nova's native Qwen tokenizer path does not need it.
The required direct runtime packages are pinned in `requirements.txt` and
`requirements-embedded.txt`.

## Background workspace compaction

Live mode does not scan workspace files by default. To opt in, set
`NOVA_COMPACTOR_ROOTS` to one or more colon-separated project directories
inside Nova's approved workspaces. Nova stores summaries of matching files in
its local memory database; do not include folders containing material you do
not want summarized.

## Long tasks

Nova allows up to `NOVA_MAX_AGENT_STEPS` agent steps per request (default 100,
maximum 1000). If it reaches that limit or the model becomes unavailable, it
prints a task ID and saves a checkpoint. Resume it in a later process with:

```bash
claw continue <task-id>
```

Paused task IDs can also be listed with `claw jobs --status PAUSED`. Remove a
paused or completed task and its saved context with `claw discard-task <task-id>`;
active tasks cannot be discarded.

Task context is kept in Nova's local jobs database while the task is active or
paused and cleared when it completes. A tool interrupted before its result was
saved is not repeated automatically; Nova is told to inspect the current state
first. Terminal commands default to 120 seconds and may request up to 1800
seconds for long builds.

**Terminal safety limitation:** Nova validates the command's working directory,
but macOS does not provide this Python CLI with a supported OS-level shell
sandbox. Shell commands still run with the user's permissions and may access
other files. Do not treat the working-directory check as filesystem isolation.

## Optional always-on LaunchAgent

Generate a plist for this checkout and the currently active Python environment:

```bash
./venv/bin/python scripts/install_launchd.py
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.deepclaw.nova.plist"
```

The generator writes the plist but does not load it. `KeepAlive` restarts Nova
after a crash; paused tasks still require `claw continue <task-id>` and are not
automatically resumed.

After installation:

```bash
claw status
claw "inspect the current repository and report its health"
```
