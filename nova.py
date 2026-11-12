#!/usr/bin/env python3
"""
Nova-Claw - Main Unified System Controller & Voice Agent CLI
Designed for Mac M5 (32GB Unified Memory Architecture).
Supports:
- Model Auto-Tuning, Selection & Downloading (Gemma, Qwen, DeepSeek, gpt-oss / get-oss)
- Restored Interactive `claw hud` Agentic Runner
- Open-Source Whisper STT & Zero-Shot Voice Clone TTS with `--additional-flags`
- Desktop Note Creation (`~/Desktop/DeepClaw_Notes`), App Takeover, and Plugin Management
"""

import sys
import os
import json
import argparse
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

import config
from core.telemetry import get_system_metrics
from core.throttling import UnifiedMemoryGovernor
from core.residency import ModelResidencyManager
from core.harness import auto_tune_environment, get_harness_profile
from core.model_manager import (
    discover_local_models,
    select_and_tune_model,
    download_model_weights,
)
from core.hud import run_hud
from core.static_router import save_note_to_desktop
from memory.compactor import ContinuousCompactor
from memory.db import MemoryStore
from training.trainer import ModelTrainer
from tools.system import clean_system_caches, get_system_health
from voice.assistant import NovaVoiceAssistant
from core.job_store import JobStore

NOVA_CLI_API = "1"


def _build_assistant_from_args(args: argparse.Namespace) -> NovaVoiceAssistant:
    extra_flags = config.parse_additional_flags(getattr(args, "additional_flags", None))
    if getattr(args, "model", None):
        select_and_tune_model(args.model, backend=getattr(args, "backend", None), persist=False)
    return NovaVoiceAssistant(
        model_name=getattr(args, "model", None) or config.DEFAULT_MODEL,
        whisper_model=getattr(args, "whisper_model", None),
        whisper_backend=getattr(args, "whisper_backend", None),
        voice_name=getattr(args, "voice_name", None),
        tts_backend=getattr(args, "tts_backend", None),
        voice_clone_model=getattr(args, "voice_clone_model", None),
        voice_clone_ref=getattr(args, "voice_clone_ref", None),
        voice_clone_text=getattr(args, "voice_clone_text", None),
        additional_flags=extra_flags,
    )


def cmd_status():
    metrics = get_system_metrics()
    health = get_system_health()
    residency = ModelResidencyManager()
    profile = get_harness_profile(config.DEFAULT_MODEL)
    if config.MODEL_BACKEND != "embedded":
        try:
            residency.ensure_resident()
            residency.start_residency_watchdog()
        except Exception:
            pass
    store = MemoryStore()

    print("\033[1;36m====================================================================\033[0m")
    print("\033[1;37m 🐺 NOVA-CLAW · APPLE SILICON M5 MISSION CONTROL\033[0m")
    print("\033[1;36m====================================================================\033[0m")
    print(f"\033[1;33m[UNIFIED MEMORY & HARDWARE (32GB UMA · +5% STRICT GOVERNOR)]\033[0m")
    print(f"  • Host Unified RAM : {metrics['used_ram_mb']:.1f} MB used / {metrics['total_ram_mb']:.1f} MB total ({metrics['avail_ram_mb']:.1f} MB free)")
    print(f"  • Safe RAM Ceiling : {config.MAX_SAFE_RAM_MB:.1f} MB (Reserve: {config.RESERVE_RAM_MB:.1f} MB)")
    print(f"  • macOS Swap Space : {metrics['swap_used_mb']:.1f} MB active (Trigger: {config.MAX_SWAP_MB:.1f} MB)")
    print(f"  • Disk Free Space  : {health['disk_free_gb']} GB / {health['disk_total_gb']} GB")
    print(f"  • Desktop Notes Dir: {config.DESKTOP_STORAGE_DIR}")
    print(f"  • Metal GPU Core   : {metrics.get('gpu_arch', 'Apple M5 Metal')} [ACTIVE]")
    sme_str = "ACTIVE (FEAT_SME / SME2)" if metrics.get("cpu_sme_active") else "STANDBY"
    print(f"  • CPU Matrix/SME   : {sme_str}")

    print(f"\033[1;34m[NEURAL MODEL RESIDENCY & AUTO-TUNING]\033[0m")
    if config.MODEL_BACKEND == "embedded":
        res_str = "\033[1;32m● EMBEDDED MLX (LAZY LOAD)\033[0m"
    elif config.MODEL_BACKEND == "omlx":
        res_str = "\033[1;32m● MANAGED BY LOCAL oMLX\033[0m"
    else:
        is_res = residency.is_model_loaded()
        res_str = "\033[1;32m● RESIDENT (LOCKED IN RAM)\033[0m" if is_res else "\033[1;31m○ STANDBY (NOT PINNED)\033[0m"
    print(f"  • Model Name       : {config.DEFAULT_MODEL}")
    print(f"  • Detected Family  : {profile.family.upper()} (temp={profile.temperature}, top_p={profile.top_p}, kv_slots={profile.kv_cache_slots})")
    print(f"  • Residency Status : {res_str}")
    endpoint = (
        "in-process"
        if config.MODEL_BACKEND == "embedded"
        else config.OMLX_URL if config.MODEL_BACKEND == "omlx" else config.OLLAMA_URL
    )
    print(f"  • Model Backend    : {config.MODEL_BACKEND}")
    print(f"  • Engine Endpoint  : {endpoint}")
    print(f"  • Voice / Whisper  : STT={config.WHISPER_MODEL} ({config.WHISPER_BACKEND}) | TTS={config.VOICE_CLONE_MODEL or config.VOICE_NAME}")

    print(f"\033[1;35m[KNOWLEDGE & MEMORY RETENTION]\033[0m")
    with store.get_connection() as conn:
        m_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        f_count = conn.execute("SELECT COUNT(*) FROM file_compaction").fetchone()[0]
        s_count = conn.execute("SELECT COUNT(*) FROM skills_ledger").fetchone()[0]
        t_count = conn.execute("SELECT COUNT(*) FROM training_traces").fetchone()[0]

    print(f"  • Synthesized Memories : {m_count} records")
    print(f"  • Compacted Documents  : {f_count} files")
    print(f"  • Self-Authored Skills : {s_count} active tools")
    print(f"  • Execution Traces     : {t_count} training samples")
    print("\033[1;36m====================================================================\033[0m")


def cmd_ask(prompt: str, voice: bool = True, args: Optional[argparse.Namespace] = None):
    assistant = _build_assistant_from_args(args) if args else NovaVoiceAssistant()
    print(f"\n\033[1;34mUser:\033[0m {prompt}")
    ans = assistant.process_command(prompt, voice_output=voice)
    st = assistant.last_stats
    if st.get("tokens_per_sec"):
        print(f"  \033[90m[{st.get('eval_count', 0)} gen tok @ {st['tokens_per_sec']} tok/s · KV cached {st.get('cached_tokens', 0)}/{st.get('prompt_tokens', 0)} · {st.get('duration_sec', 0)}s]\033[0m")
    elif st.get("tokens_saved"):
        print(f"  \033[90m[Static Router Hit · Saved ~{st['tokens_saved']} LLM tokens · 0.00s]\033[0m")
    print(f"\033[1;32mNova:\033[0m {ans}\n")


def cmd_continue(task_id: str, voice: bool = True):
    assistant = NovaVoiceAssistant()
    ans = assistant.resume_task(task_id, voice_output=voice)
    print(f"\033[1;32mNova:\033[0m {ans}\n")


def cmd_discard_task(task_id: str):
    if JobStore().delete_agent_task(task_id):
        print(f"Discarded task {task_id} and its checkpoint.")
    else:
        print(f"Task {task_id} was not found or is still active.")


def cmd_model(action: str = "list", target: Optional[str] = None, backend: Optional[str] = None, extra_flags: Optional[List[str]] = None, revision: Optional[str] = None):
    act = (action or "list").lower()
    if act == "list":
        print("\033[1;36m=== CURATED AUTO-TUNED MODEL FAMILIES ===\033[0m")
        for key, info in config.MODEL_CATALOG.items():
            marker = "★ ACTIVE" if info["repo_id"] == config.DEFAULT_MODEL else " "
            print(f"  [{key:<8}] {info['repo_id']} {marker}")
            print(f"             • {info['description']}")
            print(f"             • Auto-Tune: temp={info['temperature']}, top_p={info['top_p']}, ctx={info['max_context_tokens']}, kv_slots={info['kv_slots']}")
        local = discover_local_models()
        if local:
            print("\n\033[1;33m=== LOCALLY DISCOVERED MODELS ON DEVICE ===\033[0m")
            for item in local:
                print(f"  • [{item['family'].upper():<8}] {item['name']} -> {item['path']}")
        return

    if act in ("select", "use", "tune"):
        if not target:
            print("Error: specify a model family (gemma, qwen, deepseek, gpt-oss / get-oss) or repo ID.")
            return
        tuned = select_and_tune_model(target, backend=backend, persist=True)
        print(f"\033[1;32m✔ Auto-tuned environment for model:\033[0m {tuned['model_name']}")
        print(json.dumps(tuned, indent=2))
        return

    if act in ("download", "pull"):
        if not target:
            print("Error: specify a model family (gemma, qwen, deepseek, gpt-oss / get-oss) or HF repo ID to download.")
            return
        print(f"⬇ Downloading model '{target}' into {config.MODELS_DIR} and auto-tuning environment...")
        res = download_model_weights(target, additional_flags=extra_flags, revision=revision)
        print(json.dumps(res, indent=2))
        return


def cmd_repl(voice: bool = False, args: Optional[argparse.Namespace] = None):
    assistant = _build_assistant_from_args(args) if args else NovaVoiceAssistant()
    print("\033[1;35m╭────────────────────────────────────────────────────────────────────╮\033[0m")
    print("\033[1;35m│\033[0m  \033[1;37m🐺 CLAW / NOVA · Interactive Agent REPL (Apple M5 MLX)\033[0m            \033[1;35m│\033[0m")
    print("\033[1;35m│\033[0m  Commands: /clear, /status, /hud, /jobs, /model <name>, /note     \033[1;35m│\033[0m")
    print("\033[1;35m│\033[0m            /continue <id>, /discard-task <id>, /exit               \033[1;35m│\033[0m")
    print("\033[1;35m╰────────────────────────────────────────────────────────────────────╯\033[0m")
    while True:
        try:
            line = input("\n\033[1;34mclaw>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL.")
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/clear":
            assistant.reset_history()
            print("Conversation history cleared.")
            continue
        if line == "/status":
            cmd_status()
            continue
        if line == "/hud":
            run_hud(assistant=assistant, once=False, voice=voice)
            continue
        if line == "/jobs":
            cmd_jobs()
            continue
        if line.startswith("/model"):
            arg = line.partition(" ")[2].strip()
            if not arg or arg == "list":
                cmd_model("list")
            else:
                tuned = select_and_tune_model(arg)
                assistant.residency.model_name = tuned["model_name"]
                print(f"Switched & auto-tuned model: {tuned['model_name']} ({tuned['family']})")
            continue
        if line.startswith("/note "):
            note_body = line.partition(" ")[2].strip()
            p = save_note_to_desktop(title=f"repl_note_{int(time.time())}", content=note_body)
            print(f"Saved note to Desktop folder: {p}")
            continue
        if line.startswith("/continue "):
            task_id = line.partition(" ")[2].strip()
            ans = assistant.resume_task(task_id, voice_output=voice)
            print(f"\033[1;32mNova:\033[0m {ans}")
            continue
        if line.startswith("/discard-task "):
            cmd_discard_task(line.partition(" ")[2].strip())
            continue
        ans = assistant.process_command(line, voice_output=voice)
        st = assistant.last_stats
        if st.get("tokens_per_sec"):
            print(f"  \033[90m[{st.get('eval_count', 0)} tok · {st['tokens_per_sec']} tok/s · {st.get('duration_sec', 0)}s]\033[0m")
        elif st.get("tokens_saved"):
            print(f"  \033[90m[Static Router · Saved ~{st['tokens_saved']} tok]\033[0m")
        print(f"\033[1;32mNova:\033[0m {ans}")


def cmd_live(mode=None, args: Optional[argparse.Namespace] = None):
    mode = mode or config.VOICE_MODE
    if mode not in ("hands-free", "push-to-talk"):
        raise ValueError("voice mode must be hands-free or push-to-talk")
    print(f"\033[1;35mStarting Nova-Claw voice assistant ({mode})...\033[0m")
    assistant = _build_assistant_from_args(args) if args else NovaVoiceAssistant()
    assistant.residency.start_residency_watchdog()
    compactor = ContinuousCompactor()

    assistant.tts.speak("Nova-Claw online. I am listening.")
    if mode == "hands-free":
        print("Nova is active. Speak commands (wake words: " + ", ".join(config.WAKE_WORDS) + ") or press Ctrl+C to stop.")
    else:
        print("Nova is active. Press Enter to record, or type /exit to stop.")

    last_sweep = time.time()
    try:
        while True:
            if mode == "push-to-talk":
                command = input("\n[Enter] record · [/exit] stop: ").strip().lower()
                if command in ("/exit", "/quit"):
                    break
            audio_file = assistant.stt.record_microphone(duration_seconds=config.VOICE_RECORD_SECONDS)
            if audio_file:
                try:
                    transcript = assistant.stt.transcribe_audio_file(audio_file).strip()
                finally:
                    audio_file.unlink(missing_ok=True)
                low = transcript.lower()
                if transcript and not transcript.startswith("[Speech") and (
                    mode == "push-to-talk" or any(w in low for w in config.WAKE_WORDS)
                ):
                    print(f"\n\033[1;34mHeard:\033[0m {transcript}")
                    ans = assistant.process_command(transcript, voice_output=True)
                    print(f"\033[1;32mNova:\033[0m {ans}")

            if time.time() - last_sweep > 300:
                compactor.run_sweep()
                compactor.synthesize_round()
                last_sweep = time.time()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nNova stopping gracefully.")
        assistant.residency.stop_residency_watchdog()


def cmd_train():
    print("\033[1;33mInitiating On-Device Training Round via Apple Metal...\033[0m")
    trainer = ModelTrainer()
    res = trainer.train_lora_round()
    print(f"Training Result: {res['status']}")
    if "duration_seconds" in res:
        print(f"Trained {res.get('traces_trained', 0)} traces in {res['duration_seconds']:.2f}s.")
    if "adapter_path" in res:
        print(f"LoRA Adapter saved to: {res['adapter_path']}")


def cmd_clean():
    res = clean_system_caches()
    print(f"Reclaimed {res['reclaimed_mb']:.2f} MB from system caches.")


def cmd_benchmark():
    from benchmarks.harness_benchmark import run_benchmark
    result = run_benchmark()
    print(f"Harness benchmark: {result['passed']}/{result['total']}")
    for name, passed in result["checks"].items():
        print(f"  {'PASS' if passed else 'FAIL'} {name}")
    return result["passed"] == result["total"]


def cmd_doctor() -> int:
    checks = {
        "nova.py": Path(__file__).is_file(),
        "config": Path(config.__file__).is_file(),
        "model": bool(config.DEFAULT_MODEL),
        "notes_dir": config.DESKTOP_STORAGE_DIR.parent.exists(),
    }
    print("Nova-Claw doctor")
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    return 0 if all(checks.values()) else 1


def cmd_jobs(status=None, limit=50):
    store = JobStore()
    jobs = store.list_jobs(limit=limit, status=status)
    if not jobs:
        print("No jobs found.")
        return
    print(f"{'JOB ID':<18} {'STATUS':<16} {'CLASS':<12} {'OWNER':<10} {'RETRIES':<8}")
    print("-" * 70)
    for j in jobs:
        print(f"{j['job_id']:<18} {j['status']:<16} {j['resource_class']:<12} {j['owner']:<10} {j['retry_count']:<8}")


def _add_shared_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", type=str, default=None, help="Select/override model (gemma, qwen, deepseek, gpt-oss / get-oss, or HF repo)")
    parser.add_argument("--backend", type=str, choices=("embedded", "mlx", "omlx", "ollama"), default=None, help="Override model backend")
    parser.add_argument("--whisper-model", type=str, default=None, help="Open-source Whisper model (e.g. base.en, small.en, large-v3-turbo)")
    parser.add_argument("--whisper-backend", type=str, default=None, help="Whisper engine (auto, mlx_whisper, openai_whisper, faster_whisper, whisper_cpp)")
    parser.add_argument("--voice-clone-model", type=str, default=None, help="Zero-shot voice clone TTS model (e.g. mlx-community/F5-TTS, chatterbox, xtts_v2)")
    parser.add_argument("--voice-clone-ref", type=str, default=None, help="Path to reference .wav audio file for voice cloning")
    parser.add_argument("--voice-clone-text", type=str, default=None, help="Transcript of reference audio for voice cloning")
    parser.add_argument("--tts-backend", type=str, default=None, help="TTS backend (auto, voice_clone, mlx_audio, xtts, macos_say)")
    parser.add_argument("--voice-name", type=str, default=None, help="Fallback macOS voice name (default: Samantha)")
    parser.add_argument("--additional-flags", type=str, action="append", default=[], help="Pass-through flags for Whisper, Voice Clone, or LLM engine")
    parser.add_argument("--model-revision", type=str, default=None, help="Immutable Hugging Face revision required for model downloads")


def main():
    parser = argparse.ArgumentParser(description="Nova-Claw System Controller (Mac M5)")
    parser.add_argument("--api-version", action="version", version=NOVA_CLI_API)
    _add_shared_runtime_flags(parser)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Display hardware, memory, auto-tune, and model status")

    hud_p = subparsers.add_parser("hud", help="Launch live full-screen Mission Control HUD & Agentic Runner")
    hud_p.add_argument("--once", action="store_true", help="Render single HUD snapshot and exit")
    hud_p.add_argument("--voice", action="store_true", help="Enable spoken voice output in HUD")
    _add_shared_runtime_flags(hud_p)

    repl_p = subparsers.add_parser("repl", help="Start interactive multi-turn agent REPL")
    repl_p.add_argument("--voice", action="store_true", help="Enable spoken voice output in REPL")
    _add_shared_runtime_flags(repl_p)

    live_p = subparsers.add_parser("live", help="Run live voice assistant loop (Whisper STT + Voice Clone / TTS)")
    live_p.add_argument("--mode", choices=("hands-free", "push-to-talk"), default=None)
    _add_shared_runtime_flags(live_p)

    model_p = subparsers.add_parser("model", help="Choose, auto-tune, list, or download models (gemma, qwen, deepseek, gpt-oss / get-oss)")
    model_p.add_argument("action", nargs="?", choices=("list", "select", "use", "tune", "download", "pull"), default="list")
    model_p.add_argument("target", nargs="?", default=None, help="Model family (gemma, qwen, deepseek, gpt-oss, get-oss) or repo ID")
    _add_shared_runtime_flags(model_p)

    dl_p = subparsers.add_parser("download-model", help="Download a model (gemma, qwen, deepseek, gpt-oss / get-oss) and auto-tune environment")
    dl_p.add_argument("target", type=str, help="Model family or Hugging Face repo ID")
    _add_shared_runtime_flags(dl_p)

    note_p = subparsers.add_parser("note", help="Save a note or text directly into ~/Desktop/DeepClaw_Notes")
    note_p.add_argument("title", type=str, help="Note title or filename")
    note_p.add_argument("content", type=str, help="Text content to save")
    note_p.add_argument("--subfolder", type=str, default="", help="Optional subfolder on Desktop")

    subparsers.add_parser("train", help="Run on-device fine-tuning round")
    subparsers.add_parser("clean", help="Clean developer and app caches")
    subparsers.add_parser("benchmark", help="Run deterministic harness checks")
    subparsers.add_parser("doctor", help="Check the Nova installation and runtime configuration")
    subparsers.add_parser("agent-card", help="Print Google A2A /.well-known/agent.json card")
    a2a_p = subparsers.add_parser("serve-a2a", help="Serve the local A2A JSON-RPC/SSE daemon")
    a2a_p.add_argument("--port", type=int, default=8090)

    jobs_p = subparsers.add_parser("jobs", help="List governor jobs")
    jobs_p.add_argument("--status", type=str, default=None)
    jobs_p.add_argument("--limit", type=int, default=50)

    ask_p = subparsers.add_parser("ask", help="Send a command or prompt")
    ask_p.add_argument("query", type=str, help="Text instruction for Nova")
    ask_p.add_argument("--no-voice", action="store_true", help="Disable voice speech output")
    _add_shared_runtime_flags(ask_p)

    continue_p = subparsers.add_parser("continue", help="Resume a paused or interrupted agent task")
    continue_p.add_argument("task_id", type=str, help="Task ID printed when Nova paused")
    continue_p.add_argument("--no-voice", action="store_true", help="Disable voice speech output")

    discard_p = subparsers.add_parser("discard-task", help="Delete a paused/completed task and its checkpoint")
    discard_p.add_argument("task_id", type=str, help="Agent task ID")

    args = parser.parse_args()
    if args.command == "status" or not args.command:
        if getattr(args, "model", None):
            select_and_tune_model(args.model, backend=getattr(args, "backend", None), persist=False)
        cmd_status()
    elif args.command == "hud":
        assistant = _build_assistant_from_args(args)
        run_hud(assistant=assistant, once=args.once, voice=args.voice)
    elif args.command == "repl":
        cmd_repl(voice=args.voice, args=args)
    elif args.command == "ask":
        cmd_ask(args.query, voice=not args.no_voice, args=args)
    elif args.command == "model":
        cmd_model(
            action=args.action,
            target=args.target or args.model,
            backend=args.backend,
            extra_flags=config.parse_additional_flags(args.additional_flags),
            revision=args.model_revision,
        )
    elif args.command == "download-model":
        cmd_model(
            action="download",
            target=args.target,
            backend=args.backend,
            extra_flags=config.parse_additional_flags(args.additional_flags),
            revision=args.model_revision,
        )
    elif args.command == "note":
        saved = save_note_to_desktop(title=args.title, content=args.content, subfolder=args.subfolder)
        print(f"Saved note to Desktop folder: {saved}")
    elif args.command == "agent-card":
        print(json.dumps(NovaVoiceAssistant().get_agent_card(), indent=2))
    elif args.command == "serve-a2a":
        from core.a2a_server import serve_a2a
        serve_a2a(port=args.port)
    elif args.command == "continue":
        cmd_continue(args.task_id, voice=not args.no_voice)
    elif args.command == "discard-task":
        cmd_discard_task(args.task_id)
    elif args.command == "live":
        cmd_live(mode=args.mode, args=args)
    elif args.command == "train":
        cmd_train()
    elif args.command == "clean":
        cmd_clean()
    elif args.command == "benchmark":
        raise SystemExit(0 if cmd_benchmark() else 1)
    elif args.command == "doctor":
        raise SystemExit(cmd_doctor())
    elif args.command == "jobs":
        cmd_jobs(status=args.status, limit=args.limit)


if __name__ == "__main__":
    main()
