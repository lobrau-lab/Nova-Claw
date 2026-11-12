#!/usr/bin/env python3
"""
Nova-Claw Configuration
Tailored for Apple Silicon (Mac M5, 32GB Unified Memory Architecture).
Includes +5% tightened safety constraints, Desktop note storage,
model auto-tuning registry, and Whisper / Voice Clone configuration.
"""

import os
import json
import shlex
from pathlib import Path
from typing import Dict, Any, List

# System Directories
APP_DIR = Path.home() / ".deepclaw"

# Dedicated Desktop folder for creating notes and saving text/artifacts
DESKTOP_DIR = Path.home() / "Desktop"
DESKTOP_STORAGE_DIR = Path(
    os.getenv("NOVA_DESKTOP_STORAGE_DIR", str(DESKTOP_DIR / "DeepClaw_Notes"))
).expanduser()

WORKSPACE_ROOTS = [
    Path.home() / "workspace",
    Path.home() / "projects",
    DESKTOP_DIR,
    DESKTOP_STORAGE_DIR,
    Path.home() / "Documents" / "DeepClaw",
    APP_DIR,
    Path("/tmp"),
]
COMPACTOR_ROOTS = [
    Path(p).expanduser().resolve()
    for p in os.getenv("NOVA_COMPACTOR_ROOTS", "").split(os.pathsep)
    if p.strip()
]

def ensure_desktop_storage_dir(subfolder: str = "") -> Path:
    """Ensures the Desktop storage folder exists for notes and saved text."""
    target = DESKTOP_STORAGE_DIR / subfolder if subfolder else DESKTOP_STORAGE_DIR
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except Exception:
        fallback = APP_DIR / "Desktop_Notes" / subfolder if subfolder else APP_DIR / "Desktop_Notes"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

def _resolve_safe_db_path(default_path: Path) -> Path:
    env_override = os.getenv("NOVA_DB_PATH")
    if env_override:
        return Path(env_override)
    return default_path

# Database & Storage
DB_PATH = _resolve_safe_db_path(APP_DIR / "nova_memory.db")
TRAINING_DIR = APP_DIR / "training"
SKILLS_DIR = APP_DIR / "skills"
PLUGINS_DIR = APP_DIR / "plugins"
MODELS_DIR = Path(os.getenv("NOVA_MODELS_DIR", str(DESKTOP_DIR / "DeepClaw_Models"))).expanduser()
LOGS_DIR = APP_DIR / "logs"
MEMORY_MARKDOWN_PATH = APP_DIR / "memory.md"
MODEL_STATE_PATH = APP_DIR / "model_state.json"

# +5% Tightened Constraint Factor (0.95 ceiling / 1.05 reserve)
STRICTNESS_FACTOR = 0.95
RESERVE_STRICTNESS_FACTOR = 1.05

# 32GB Unified Memory Safety Thresholds (in MB) — tightened by 5%
TOTAL_RAM_MB = 32768.0
MAX_SAFE_RAM_MB = round(28160.0 * STRICTNESS_FACTOR, 1)        # 26752.0 MB (~6.0GB headroom)
RESERVE_RAM_MB = round(3072.0 * RESERVE_STRICTNESS_FACTOR, 1)  # 3225.6 MB minimum reserve before hard throttle
MAX_SWAP_MB = round(2048.0 * STRICTNESS_FACTOR, 1)             # 1945.6 MB swap trigger point
BASE_DYNAMIC_DELAY = round(0.05 * RESERVE_STRICTNESS_FACTOR, 4) # 0.0525s base interval

# Context/memory lifecycle — tightened by 5%
MAX_CONTEXT_TOKENS = int(os.getenv("NOVA_MAX_CONTEXT_TOKENS", "16384"))
CONTEXT_ROLLOVER_RATIO = float(os.getenv("NOVA_CONTEXT_ROLLOVER_RATIO", "0.855"))   # 5% stricter than 0.90
CONTEXT_ROLLOVER_FRACTION = float(os.getenv("NOVA_CONTEXT_ROLLOVER_FRACTION", "0.40"))
MEMORY_COMPACTION_INTERVAL_SECONDS = int(os.getenv("NOVA_MEMORY_COMPACTION_INTERVAL", "3420"))  # 5% stricter than 3600
MEMORY_COMPACTION_MAX_CHARS = int(os.getenv("NOVA_MEMORY_MAX_CHARS", "22800"))      # 5% stricter than 24000
MAX_AGENT_STEPS = min(950, max(1, int(os.getenv("NOVA_MAX_AGENT_STEPS", "95"))))    # 5% stricter than 100/1000
MAX_COMMAND_TIMEOUT_SECONDS = 1800
DEFAULT_COMMAND_TIMEOUT_SECONDS = min(
    MAX_COMMAND_TIMEOUT_SECONDS,
    max(1, int(os.getenv("NOVA_COMMAND_TIMEOUT_SECONDS", "114"))),                  # 5% stricter than 120s
)
MAX_TOOL_OUTPUT_CHARS = int(os.getenv("NOVA_MAX_TOOL_OUTPUT_CHARS", "5700"))        # 5% stricter than 6000
MAX_TRACE_RESULT_CHARS = int(os.getenv("NOVA_MAX_TRACE_RESULT_CHARS", "3800"))      # 5% stricter than 4000

# KV prefix cache budget — tightened by 5%
KV_CACHE_SLOTS = int(os.getenv("NOVA_KV_SLOTS", "8"))
KV_CACHE_MAX_BYTES = int(MAX_SAFE_RAM_MB * (0.25 * STRICTNESS_FACTOR) * 1024 * 1024)

# Curated Model Catalog for Choice, Download & Auto-Tuning
MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "qwen2.5": {
        "family": "qwen",
        "variant": "qwen2.5",
        "repo_id": "mlx-community/Qwen2.5-Coder-32B-Instruct-4bit",
        "aliases": ["qwen2.5", "qwen-2.5", "qwen25", "qwen2.5-coder"],
        "backend": "embedded",
        "temperature": 0.2,
        "top_p": 0.85,
        "max_tokens": 1536,
        "max_context_tokens": 16384,
        "kv_slots": 8,
        "enable_thinking": False,
        "description": "Qwen 2.5 Coder 32B (4-bit MLX) — stable coding fallback.",
    },
    "qwen3.5": {
        "family": "qwen",
        "variant": "qwen3.5",
        "repo_id": "mlx-community/Qwen3.5-35B-A3B-4bit",
        "aliases": ["qwen3.5", "qwen-3.5", "qwen35"],
        "backend": "embedded",
        "temperature": 0.2,
        "top_p": 0.85,
        "max_tokens": 1536,
        "max_context_tokens": 16384,
        "kv_slots": 10,
        "enable_thinking": False,
        "description": "Qwen 3.5 35B-A3B MoE (4-bit MLX) — preferred capable coding model.",
    },
    "qwen": {
        "family": "qwen",
        "variant": "qwen3.5",
        "repo_id": "mlx-community/Qwen3.5-35B-A3B-4bit",
        "aliases": ["qwen", "qwen3", "qwen-35b"],
        "backend": "embedded",
        "temperature": 0.2,
        "top_p": 0.85,
        "max_tokens": 1536,
        "max_context_tokens": 16384,
        "kv_slots": 10,
        "enable_thinking": False,
        "description": "Qwen 3.5 35B-A3B MoE (4-bit MLX) — Fast coding, XML+JSON tool use, low memory active footprint.",
    },
    "gemma3": {
        "family": "gemma",
        "variant": "gemma3",
        "repo_id": "mlx-community/gemma-3-27b-it-4bit",
        "aliases": ["gemma3", "gemma-3", "gemma-27b"],
        "backend": "embedded",
        "temperature": 0.3,
        "top_p": 0.92,
        "max_tokens": 1024,
        "max_context_tokens": 16384,
        "kv_slots": 6,
        "enable_thinking": False,
        "description": "Gemma 3 27B Instruct (4-bit MLX) — efficient instruction model.",
    },
    "gemma4": {
        "family": "gemma",
        "variant": "gemma4",
        "repo_id": "mlx-community/gemma-4-E4B-it-4bit",
        "aliases": ["gemma4", "gemma-4"],
        "backend": "embedded",
        "temperature": 0.3,
        "top_p": 0.92,
        "max_tokens": 1536,
        "max_context_tokens": 16384,
        "kv_slots": 6,
        "enable_thinking": False,
        "description": "Gemma 4 E4B Instruct (4-bit MLX) — higher-capability general model.",
    },
    "gemma": {
        "family": "gemma",
        "variant": "gemma3",
        "repo_id": "mlx-community/gemma-3-27b-it-4bit",
        "omlx_id": "gemma-4-E4B-it-ultra-uncensored-heretic-MLX-4bit-mixed_4_6",
        "aliases": ["gemma", "gemma-31b"],
        "backend": "embedded",
        "temperature": 0.3,
        "top_p": 0.92,
        "max_tokens": 1024,
        "max_context_tokens": 16384,
        "kv_slots": 6,
        "enable_thinking": False,
        "description": "Gemma 3/4 Instruct (4-bit MLX) — High precision instruction following & single-step verified edits.",
    },
    "deepseek": {
        "family": "deepseek",
        "repo_id": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit",
        "aliases": ["deepseek", "deepseek-r1", "deepseek-v3", "deepseek-coder", "r1"],
        "backend": "mlx",
        "temperature": 0.3,
        "top_p": 0.90,
        "max_tokens": 2048,
        "max_context_tokens": 16384,
        "kv_slots": 8,
        "enable_thinking": True,
        "description": "DeepSeek R1 Distill 32B (4-bit MLX) — Deep multi-step reasoning, debugging, and math/architecture verification.",
    },
    "gpt-oss": {
        "family": "gpt-oss",
        "repo_id": "mlx-community/gpt-oss-20b-4bit",
        "aliases": ["gpt-oss", "gpt-oss:20b", "gpt-oss-20b", "get-oss", "gpt_oss", "get_oss", "openai-oss", "gpt"],
        "backend": "mlx",
        "temperature": 0.25,
        "top_p": 0.90,
        "max_tokens": 1536,
        "max_context_tokens": 16384,
        "kv_slots": 8,
        "enable_thinking": False,
        "description": "GPT-OSS / get-oss 20B (4-bit MLX) — Open-weights OpenAI Harmony-format tool use and structured synthesis.",
    },
}

def _local_omlx_api_key() -> str:
    """Reuse the local oMLX key without placing credentials in source or logs."""
    settings_path = Path.home() / ".omlx" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        return str(settings.get("auth", {}).get("api_key", ""))
    except (OSError, ValueError, TypeError):
        return ""

def load_persisted_model_state() -> Dict[str, Any]:
    try:
        if MODEL_STATE_PATH.is_file():
            return json.loads(MODEL_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

# Model & Neural Runtime
MODEL_BACKEND = os.getenv("NOVA_MODEL_BACKEND", "embedded").lower()
OMLX_URL = os.getenv("OMLX_URL", "http://127.0.0.1:8000").rstrip("/")
OMLX_API_KEY = os.getenv("OMLX_API_KEY") or _local_omlx_api_key()
ENABLE_OFFLINE_FALLBACK = os.getenv("NOVA_ENABLE_OFFLINE_FALLBACK", "0") == "1"
ENABLE_EXTERNAL_SKILLS = os.getenv("NOVA_ENABLE_EXTERNAL_SKILLS", "1") == "1"
ENABLE_DYNAMIC_SKILLS = os.getenv("NOVA_ENABLE_DYNAMIC_SKILLS", "0") == "1"
AUTO_TUNE_ENABLED = os.getenv("NOVA_AUTO_TUNE", "1") == "1"

EMBEDDED_MODEL = os.getenv("NOVA_MODEL", "mlx-community/Qwen3.5-35B-A3B-4bit")
OMLX_MODEL = os.getenv("NOVA_OMLX_MODEL", "gemma-4-E4B-it-ultra-uncensored-heretic-MLX-4bit-mixed_4_6")
DEFAULT_MODEL = EMBEDDED_MODEL if MODEL_BACKEND == "embedded" else OMLX_MODEL
MLX_MODEL_PATH = os.getenv("NOVA_MLX_MODEL", EMBEDDED_MODEL)

# Retained for callers that still use the legacy Ollama configuration name.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
if os.getenv("NOVA_OFFLINE", "0") == "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
MODEL_KEEP_ALIVE = 99

# Voice, Open-Source Whisper STT & Voice Clone TTS
WAKE_WORDS = ["nova", "hey nova", "claw", "deepclaw"]
VOICE_NAME = os.getenv("NOVA_VOICE_NAME", "Samantha")
SPEECH_INPUT_DEVICE = os.getenv("NOVA_SPEECH_INPUT_DEVICE") or None
WHISPER_MODEL = os.getenv("NOVA_WHISPER_MODEL", "base.en")
WHISPER_BACKEND = os.getenv("NOVA_WHISPER_BACKEND", "auto")  # auto | mlx_whisper | openai_whisper | faster_whisper | whisper_cpp
TTS_BACKEND = os.getenv("NOVA_TTS_BACKEND", "auto")          # auto | voice_clone | mlx_audio | xtts | piper | macos_say
VOICE_CLONE_MODEL = os.getenv("NOVA_VOICE_CLONE_MODEL", "")  # e.g. mlx-community/F5-TTS or chatterbox or xtts_v2
VOICE_CLONE_REF_AUDIO = os.getenv("NOVA_VOICE_CLONE_REF", "")
VOICE_CLONE_REF_TEXT = os.getenv("NOVA_VOICE_CLONE_TEXT", "")
VOICE_MODE = os.getenv("NOVA_VOICE_MODE", "hands-free")
VOICE_RECORD_SECONDS = int(os.getenv("NOVA_VOICE_RECORD_SECONDS", "4"))
ADDITIONAL_FLAGS: List[str] = shlex.split(os.getenv("NOVA_ADDITIONAL_FLAGS", ""))

def parse_additional_flags(raw_flags: Any) -> List[str]:
    """Parses --additional-flags strings or lists into clean token lists."""
    if not raw_flags:
        return []
    if isinstance(raw_flags, str):
        return shlex.split(raw_flags)
    if isinstance(raw_flags, (list, tuple)):
        out: List[str] = []
        for item in raw_flags:
            out.extend(shlex.split(str(item)))
        return out
    return []

# Computer Control Safety (+5% stricter path and argument validation)
RESTRICTED_SYSTEM_PATHS = [
    "/System", "/usr/bin", "/usr/sbin", "/bin", "/sbin",
    "/Applications/Utilities", "/private/var", "/private/etc",
    "/Library/LaunchDaemons", "/Library/Security",
]
