#!/usr/bin/env python3
"""
Nova-Claw - Interactive Mission Control HUD & Agentic Runner (claw hud)
Restores and upgrades the historical `claw hud` dashboard for OpenCode-style
agentic execution on Apple Silicon M5.
Fixes the legacy Go `claw-cli/pkg/hud/hud.go` 1-second repaint bug that wiped
typed characters by maintaining a persistent raw-mode input buffer and split-pane
live telemetry + agent runner view.
"""

import os
import sys
import time
import select
import shutil
import termios
import tty
from typing import Optional, List
import config
from core.telemetry import get_system_metrics
from core.harness import get_harness_profile
from tools.system import get_system_health


def render_hud_snapshot(
    input_buffer: str = "",
    last_response: str = "",
    tokens_saved: int = 0,
    active_jobs_count: int = 0,
) -> str:
    """Builds a deterministic single-frame HUD string without erasing the user's input buffer."""
    sz = shutil.get_terminal_size((90, 28))
    width = max(72, min(sz.columns - 2, 110))
    metrics = get_system_metrics()
    health = get_system_health()
    profile = get_harness_profile(config.DEFAULT_MODEL)

    ram_pct = min(100.0, (metrics["used_ram_mb"] / max(1.0, metrics["total_ram_mb"])) * 100.0)
    filled = int((ram_pct / 100.0) * 24)
    bar = "█" * filled + "░" * (24 - filled)

    lines = [
        f"\033[1;36m╔{'═' * width}╗\033[0m",
        f"\033[1;36m║\033[0m \033[1;37m🐺 NOVA-CLAW · INTERACTIVE HUD & AGENTIC RUNNER (M5 UMA)\033[0m".ljust(width + 19) + "\033[1;36m║\033[0m",
        f"\033[1;36m╠{'═' * width}╣\033[0m",
        f"\033[1;36m║\033[0m  • UMA RAM    : [{bar}] {metrics['used_ram_mb']:.0f}/{metrics['total_ram_mb']:.0f} MB (Strict Cap: {config.MAX_SAFE_RAM_MB:.0f} MB)".ljust(width + 10) + "\033[1;36m║\033[0m",
        f"\033[1;36m║\033[0m  • Model      : {config.DEFAULT_MODEL[:48]} (Family: {profile.family.upper()} | Temp: {profile.temperature})".ljust(width + 10) + "\033[1;36m║\033[0m",
        f"\033[1;36m║\033[0m  • Voice/STT  : Whisper={config.WHISPER_MODEL} ({config.WHISPER_BACKEND}) | TTS={config.TTS_BACKEND} ({config.VOICE_NAME})".ljust(width + 10) + "\033[1;36m║\033[0m",
        f"\033[1;36m║\033[0m  • Notes Dir  : {str(config.DESKTOP_STORAGE_DIR)[:58]}".ljust(width + 10) + "\033[1;36m║\033[0m",
        f"\033[1;36m║\033[0m  • Governor   : {active_jobs_count} active job(s) | Static Router Saved: {tokens_saved} tok | Disk Free: {health['disk_free_gb']} GB".ljust(width + 10) + "\033[1;36m║\033[0m",
        f"\033[1;36m╠{'═' * width}╣\033[0m",
        f"\033[1;36m║\033[0m \033[1;33m[AGENT RUNNER STREAM]\033[0m (Commands: /model <name>, /note <text>, /status, /exit)".ljust(width + 19) + "\033[1;36m║\033[0m",
    ]

    resp_lines = (last_response or "Ready. Type any task or command below — your keystrokes are buffered across HUD refreshes.").splitlines()
    for rl in resp_lines[-6:]:
        clipped = rl[: width - 4]
        lines.append(f"\033[1;36m║\033[0m   {clipped}".ljust(width + 10) + "\033[1;36m║\033[0m")

    lines.append(f"\033[1;36m╠{'═' * width}╣\033[0m")
    prompt_str = f" claw-hud> {input_buffer}█"
    lines.append(f"\033[1;36m║\033[0m\033[1;32m{prompt_str[:width - 1].ljust(width)}\033[0m\033[1;36m║\033[0m")
    lines.append(f"\033[1;36m╚{'═' * width}╝\033[0m")
    return "\n".join(lines)


def run_hud(assistant=None, once: bool = False, voice: bool = False) -> str:
    """
    Launches the interactive full-screen `claw hud` agentic runner.
    Unlike the old Go `hud.go` which wiped typed characters every 1s refresh,
    this HUD preserves `input_buffer` in raw terminal mode and repaints it cleanly.
    """
    from voice.assistant import NovaVoiceAssistant
    agent = assistant or NovaVoiceAssistant()
    active_jobs = len(agent.governor.store.get_active_jobs())
    snapshot = render_hud_snapshot(
        input_buffer="",
        last_response="Nova-Claw HUD initialized. Persistent input bar active.",
        tokens_saved=agent.static_router.tokens_saved_total,
        active_jobs_count=active_jobs,
    )
    if once or not sys.stdin.isatty():
        print(snapshot)
        return snapshot

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    input_buf: List[str] = []
    last_resp = "Nova-Claw HUD online. Type a prompt and press Enter, or /exit to quit."

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l\033[2J")
        while True:
            active_jobs = len(agent.governor.store.get_active_jobs())
            frame = render_hud_snapshot(
                input_buffer="".join(input_buf),
                last_response=last_resp,
                tokens_saved=agent.static_router.tokens_saved_total,
                active_jobs_count=active_jobs,
            )
            sys.stdout.write("\033[H" + frame + "\033[K")
            sys.stdout.flush()

            rlist, _, _ = select.select([sys.stdin], [], [], 0.25)
            if rlist:
                ch = sys.stdin.read(1)
                if ch in ("\x03", "\x04"):  # Ctrl+C / Ctrl+D
                    break
                elif ch in ("\r", "\n"):
                    cmd = "".join(input_buf).strip()
                    input_buf.clear()
                    if cmd in ("/exit", "/quit"):
                        break
                    elif cmd.startswith("/model "):
                        from core.model_manager import select_and_tune_model
                        m_choice = cmd.partition(" ")[2].strip()
                        tuned = select_and_tune_model(m_choice)
                        agent.residency.model_name = tuned["model_name"]
                        last_resp = f"Switched & auto-tuned model -> {tuned['model_name']} ({tuned['family']})"
                    elif cmd:
                        last_resp = f"Running: {cmd} ..."
                        sys.stdout.write("\033[H" + render_hud_snapshot("", last_resp, agent.static_router.tokens_saved_total, active_jobs))
                        sys.stdout.flush()
                        last_resp = agent.process_command(cmd, voice_output=voice)
                elif ch in ("\x7f", "\b"):
                    if input_buf:
                        input_buf.pop()
                elif ch.isprintable():
                    input_buf.append(ch)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
    return last_resp
