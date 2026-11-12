#!/usr/bin/env python3
"""
Nova-Claw - Model Manager, Auto-Tuner & Downloader
Provides model discovery, selection, environment auto-tuning, and CLI downloading
for Gemma, Qwen, DeepSeek, and gpt-oss (get-oss).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import config
from core.harness import auto_tune_environment, detect_model_family, get_harness_profile


def resolve_model_choice(choice: str) -> Dict[str, Any]:
    """Resolves a shorthand family name ('gemma', 'qwen', 'deepseek', 'gpt-oss', 'get-oss') or repo ID."""
    clean = (choice or "").strip()
    low = clean.lower()
    for key, entry in config.MODEL_CATALOG.items():
        if low == key or low in [a.lower() for a in entry.get("aliases", [])]:
            return dict(entry)
    family = detect_model_family(clean)
    base = dict(config.MODEL_CATALOG.get(family, config.MODEL_CATALOG["qwen"]))
    base["repo_id"] = clean
    base["family"] = family
    return base


def discover_local_models() -> List[Dict[str, Any]]:
    """Scans local directories (~/Desktop, ~/Desktop/DeepClaw_Models, ~/.cache/huggingface) for downloaded models."""
    found: List[Dict[str, Any]] = []
    search_roots = [
        config.MODELS_DIR,
        config.DESKTOP_DIR,
        Path.home() / ".cache" / "huggingface" / "hub",
    ]
    seen = set()
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for item in root.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                low = item.name.lower()
                if any(k in low for k in ("qwen", "gemma", "deepseek", "gpt-oss", "get-oss", "llama", "mlx")):
                    resolved = str(item.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append({
                            "name": item.name,
                            "path": resolved,
                            "family": detect_model_family(item.name),
                        })
        except Exception:
            continue
    return found


def select_and_tune_model(choice: str, backend: Optional[str] = None, persist: bool = True) -> Dict[str, Any]:
    """Selects the requested model, updates config, and auto-tunes the runtime environment."""
    resolved = resolve_model_choice(choice)
    repo_id = resolved["repo_id"]
    chosen_backend = (backend or resolved.get("backend") or config.MODEL_BACKEND).lower()

    config.MODEL_BACKEND = chosen_backend
    config.EMBEDDED_MODEL = repo_id
    config.DEFAULT_MODEL = repo_id
    config.MLX_MODEL_PATH = repo_id
    os.environ["NOVA_MODEL"] = repo_id
    os.environ["NOVA_MODEL_BACKEND"] = chosen_backend

    tuned = auto_tune_environment(repo_id, persist=persist)
    tuned["backend"] = chosen_backend
    tuned["catalog_entry"] = resolved
    if persist:
        try:
            config.MODEL_STATE_PATH.write_text(json.dumps(tuned, indent=2), encoding="utf-8")
        except Exception:
            pass
    return tuned


def download_model_weights(
    choice: str,
    target_dir: Optional[Path] = None,
    additional_flags: Optional[List[str]] = None,
    revision: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Downloads a chosen model (Gemma, Qwen, DeepSeek, gpt-oss / get-oss, or HF repo ID)
    into ~/Desktop/DeepClaw_Models/<model_name> and auto-tunes the environment.
    """
    resolved = resolve_model_choice(choice)
    repo_id = resolved["repo_id"]
    revision = revision or os.getenv("NOVA_MODEL_REVISION")
    if not revision:
        return {
            "status": "FAILED",
            "repo_id": repo_id,
            "error": "Model downloads require an immutable revision (pass --model-revision or set NOVA_MODEL_REVISION).",
        }
    safe_folder = repo_id.replace("/", "--")
    dest_root = Path(target_dir or config.MODELS_DIR).expanduser()
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_path = dest_root / safe_folder

    # Allow online download explicitly when user runs the download command
    os.environ.pop("HF_HUB_OFFLINE", None)

    try:
        from huggingface_hub import snapshot_download
        local_dir = snapshot_download(
            repo_id=repo_id,
            local_dir=str(dest_path),
            revision=revision,
        )
        tuned = select_and_tune_model(str(local_dir), persist=True)
        return {
            "status": "DOWNLOADED",
            "repo_id": repo_id,
                "local_path": str(local_dir),
                "revision": revision,
            "auto_tuned": tuned,
        }
    except ImportError:
        # Fallback to huggingface-cli or ollama pull if huggingface_hub is not imported
        cmd = [sys.executable, "-m", "huggingface_hub.commands.huggingface_cli", "download", repo_id, "--revision", revision, "--local-dir", str(dest_path)]
        if additional_flags:
            cmd.extend(additional_flags)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if proc.returncode == 0:
                tuned = select_and_tune_model(str(dest_path), persist=True)
                return {
                    "status": "DOWNLOADED",
                    "repo_id": repo_id,
                    "local_path": str(dest_path),
                    "revision": revision,
                    "auto_tuned": tuned,
                }
            return {
                "status": "FAILED",
                "repo_id": repo_id,
                "error": (proc.stderr or proc.stdout).strip(),
            }
        except Exception as exc:
            return {"status": "FAILED", "repo_id": repo_id, "error": str(exc)}
    except Exception as exc:
        return {"status": "FAILED", "repo_id": repo_id, "error": str(exc)}
