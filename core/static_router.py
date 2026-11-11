#!/usr/bin/env python3
"""
DeepClaw Nova - Static Decision Router & Built-in Compute-Saving Helpers
Offloads deterministic rules, note saving, locked configurations, and quick
system/model queries into zero-token Python if/elif/else branches before LLM inference.
"""

import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
import config


DEFAULT_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "rule_desktop_notes_location",
        "category": "storage_policy",
        "description": "Default location for all notes and saved text files",
        "keywords": ["where do you save notes", "notes folder", "where are notes stored", "desktop folder for notes"],
        "static_decision": {
            "value": str(config.DESKTOP_STORAGE_DIR),
            "standard": "Desktop/DeepClaw_Notes",
            "explanation": f"All notes and saved text default to {config.DESKTOP_STORAGE_DIR} on the Desktop.",
        },
    },
    {
        "rule_id": "rule_ltx_framerate",
        "category": "video_specs",
        "description": "Standard LTX-2 and cinematic frame rate invariants",
        "keywords": ["ltx framerate", "ltx fps", "default video fps", "cinematic frame rate"],
        "static_decision": {
            "value": "50fps (LTX-2 native sync) / 24fps (SMPTE cinematic)",
            "standard": "LTX-2 50fps / SMPTE 24fps",
            "explanation": "LTX-2 desktop bridge dispatches at 50fps native sync; standard cinematic renders lock to 24fps.",
        },
    },
    {
        "rule_id": "rule_audio_ceiling",
        "category": "audio_specs",
        "description": "Locked broadcast audio loudness and true-peak ceiling",
        "keywords": ["audio ceiling", "lufs target", "true peak limit"],
        "static_decision": {
            "value": "-14.0 LUFS integrated / -1.0 dBFS true-peak",
            "standard": "ITU-R BS.1770 / EBU R128",
            "explanation": "Audio renders lock to -14 LUFS integrated with a -1.0 dBFS true-peak ceiling.",
        },
    },
    {
        "rule_id": "rule_uma_strict_budget",
        "category": "hardware_constraints",
        "description": "32GB Unified Memory +5% strict governor ceiling",
        "keywords": ["memory limit", "ram ceiling", "uma budget", "strict constraint"],
        "static_decision": {
            "value": f"{config.MAX_SAFE_RAM_MB} MB safe ceiling / {config.RESERVE_RAM_MB} MB reserve (5% stricter)",
            "standard": "Apple M5 32GB UMA (+5% Strict Governor)",
            "explanation": (
                f"Unified Memory is capped at {config.MAX_SAFE_RAM_MB} MB with a {config.RESERVE_RAM_MB} MB reserve "
                f"and {config.MAX_SWAP_MB} MB swap ceiling (+5% strict safety margin)."
            ),
        },
    },
]


def save_note_to_desktop(
    title: str,
    content: str,
    subfolder: str = "",
    extension: str = ".md",
) -> Path:
    """
    Built-in deterministic helper: always creates/uses the Desktop storage folder
    (~/Desktop/DeepClaw_Notes) when creating notes or saving text.
    """
    folder = config.ensure_desktop_storage_dir(subfolder=subfolder)
    clean_title = re.sub(r"[^a-zA-Z0-9._-]+", "_", title.strip()).strip("_") or f"note_{int(time.time())}"
    ext = extension if extension.startswith(".") else f".{extension}"
    if not clean_title.endswith((".md", ".txt", ".json", ".log")):
        clean_title += ext
    target = folder / clean_title
    target.write_text(content, encoding="utf-8")
    return target


class StaticDecisionRouter:
    """
    Zero-token deterministic if/elif/else router and rule engine.
    Evaluates user prompts before LLM inference to save compute and tokens.
    """

    def __init__(self, rules_path: Optional[Path] = None):
        self.rules_path = rules_path or (config.APP_DIR / "static_rules.json")
        self.rules: List[Dict[str, Any]] = list(DEFAULT_RULES)
        self.tokens_saved_total: int = 0
        self.hits_total: int = 0
        self._load_persisted_rules()

    def _load_persisted_rules(self) -> None:
        if not self.rules_path.is_file():
            return
        try:
            loaded = json.loads(self.rules_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_ids = {r["rule_id"] for r in self.rules}
                for item in loaded:
                    if isinstance(item, dict) and item.get("rule_id") not in existing_ids:
                        self.rules.append(item)
        except Exception:
            pass

    def add_decision_rule(
        self,
        rule_id: str,
        category: str,
        keywords: List[str],
        value: Any,
        explanation: str,
        standard: str = "User Locked Rule",
    ) -> Dict[str, Any]:
        rule = {
            "rule_id": rule_id,
            "category": category,
            "description": explanation,
            "keywords": [k.lower().strip() for k in keywords if k.strip()],
            "static_decision": {
                "value": value,
                "standard": standard,
                "explanation": explanation,
            },
        }
        self.rules = [r for r in self.rules if r.get("rule_id") != rule_id] + [rule]
        try:
            self.rules_path.parent.mkdir(parents=True, exist_ok=True)
            self.rules_path.write_text(json.dumps(self.rules, indent=2), encoding="utf-8")
        except Exception:
            pass
        return rule

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s:/._-]", " ", text.lower())).strip()

    def evaluate(
        self,
        prompt: str,
        category: Optional[str] = None,
        controller: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic if/elif/else evaluation tree:
        1. Casual greetings / thanks
        2. Direct note creation ("save note ...", "note: ...", "write a note to desktop ...")
        3. Direct deterministic system/app helpers (volume, open/quit app, quick math)
        4. Locked static decision rules
        """
        raw = prompt.strip()
        norm = self.normalize(raw)
        if not norm:
            return {"matched": False, "tokens_saved": 0, "response": ""}

        # Branch 1: Casual greeting / thanks fast-path
        if re.fullmatch(
            r"(?:hi|hello|hey|yo|thanks|thank you|good morning|good afternoon|good evening|ping|status ping)[!.?, ]*",
            raw.lower(),
        ):
            if norm.startswith(("thanks", "thank you")):
                resp = "You're welcome!"
            elif norm in ("ping", "status ping"):
                resp = "PONG — DeepClaw Nova static router active (0 LLM tokens used)."
            else:
                resp = "Hello! I'm ready to help."
            return self._record_hit(raw, resp, rule_id="casual_greeting")

        # Branch 2: Deterministic Desktop Note / Text Saver ("note: ...", "save note <title>: <text>")
        note_match = re.match(
            r"^(?:save\s+(?:a\s+)?note|create\s+(?:a\s+)?note|save\s+text|note)(?:\s+titled\s+|\s+named\s+|\s+([a-zA-Z0-9_-]+))?\s*:\s*(.+)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if note_match:
            title = (note_match.group(1) or f"note_{int(time.time())}").strip()
            body = note_match.group(2).strip()
            saved_path = save_note_to_desktop(title=title, content=body)
            resp = f"Saved note to Desktop folder: {saved_path}"
            return self._record_hit(raw, resp, rule_id="desktop_note_helper")

        # Branch 3: Deterministic Calculator / Unit Helper ("calc: 24 * 60", "calculate 1024 * 32")
        calc_match = re.match(r"^(?:calc|calculate|math)\s*:\s*([0-9+\-*/().%\s]+)$", raw, flags=re.IGNORECASE)
        if calc_match:
            expr = calc_match.group(1).strip()
            if re.fullmatch(r"[0-9+\-*/().%\s]{1,64}", expr):
                try:
                    val = eval(expr, {"__builtins__": {}}, {})
                    return self._record_hit(raw, f"{expr} = {val}", rule_id="static_math_helper")
                except Exception:
                    pass

        # Branch 4: Registered Static Decision Rules
        for rule in self.rules:
            if category and rule.get("category") != category:
                continue
            keywords = rule.get("keywords", [])
            if any(kw in norm for kw in keywords):
                dec = rule["static_decision"]
                resp = f"[{dec.get('standard', 'Locked Rule')}] {dec['explanation']} (Value: {dec['value']})"
                return self._record_hit(raw, resp, rule_id=rule["rule_id"])

        return {"matched": False, "tokens_saved": 0, "response": ""}

    def _record_hit(self, prompt: str, response: str, rule_id: str) -> Dict[str, Any]:
        # Estimate prompt + tool-schema + completion tokens bypassed (~2200 tokens when tool schemas are skipped)
        est_saved = max(256, len(prompt.split()) * 2 + len(response.split()) * 2 + 1800)
        self.tokens_saved_total += est_saved
        self.hits_total += 1
        return {
            "matched": True,
            "rule_id": rule_id,
            "source": "static_decision_router",
            "tokens_saved": est_saved,
            "response": response,
        }
