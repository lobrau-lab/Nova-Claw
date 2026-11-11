"""
Automatic Dual-Pool Memory Manager (Short-Term Pool + Long-Term Pool).
Uses built-in deterministic if-statements to automatically refresh, roll over,
persist, and compact both memory pools so the agent never has to manage memory manually.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional

import config
from memory.db import MemoryStore

CONTINUITY_TRIGGER_KEYWORDS = (
    "what we",
    "been doing",
    "earlier",
    "last time",
    "previous",
    "remember",
    "where were we",
    "refresh",
    "continue",
    "working on",
    "prior",
    "before",
    "history",
    "recap",
)


class MemoryManager:
    """
    Maintains two coordinated memory pools via deterministic if-conditions:
    1. Short-Term Pool (`short_term_pool`): bounded active session turns persisted in
       `~/.deepclaw/short_term_memory.json` and in-memory history.
    2. Long-Term Pool (`long_term_pool`): durable episodic records in SQLite (`nova_memory.db`)
       and compacted Markdown (`~/.deepclaw/memory.md`).
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        path: Optional[Path] = None,
        short_term_path: Optional[Path] = None,
    ):
        self.store = store or MemoryStore()
        self.path = path or config.MEMORY_MARKDOWN_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.short_term_path = short_term_path or (self.path.parent / "short_term_memory.json")
        self.short_term_max_messages = 12

    # ------------------------------------------------------------------
    # Pool 1: Short-Term Memory Pool Helpers
    # ------------------------------------------------------------------
    def load_short_term_pool(self) -> List[Dict[str, Any]]:
        if not self.short_term_path.is_file():
            return []
        try:
            data = json.loads(self.short_term_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[-self.short_term_max_messages:]
        except Exception:
            pass
        return []

    def save_short_term_pool(self, history: List[Dict[str, Any]]) -> None:
        bounded = list(history[-self.short_term_max_messages:])
        try:
            self.short_term_path.parent.mkdir(parents=True, exist_ok=True)
            self.short_term_path.write_text(json.dumps(bounded, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Built-in Deterministic If-Statement Context Refresh
    # ------------------------------------------------------------------
    @staticmethod
    def should_refresh_pools(user_text: str, history: List[Dict[str, Any]]) -> bool:
        """
        Deterministic if-condition: decides whether to inject full dual-pool
        refresh context without requiring the model to invoke a tool.
        """
        low = (user_text or "").strip().lower()
        if not history:
            return True
        if any(kw in low for kw in CONTINUITY_TRIGGER_KEYWORDS):
            return True
        if len(history) >= 6:
            return True
        return False

    def build_dual_pool_context(
        self,
        user_text: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Automatically assembles both Short-Term and Long-Term memory pools
        whenever `should_refresh_pools` triggers or a new turn starts.
        """
        active_history = list(history or [])
        if not active_history:
            active_history = self.load_short_term_pool()

        short_term_lines = []
        for msg in active_history[-6:]:
            role = str(msg.get("role", "user")).upper()
            content = " ".join(str(msg.get("content", "")).split())[:180]
            if content:
                short_term_lines.append(f"- [{role}] {content}")

        long_term_hits = self.store.search_memories(user_text, limit=3)
        if not long_term_hits and self.should_refresh_pools(user_text, active_history):
            # Pull latest episodic entries if user asks "what have we been doing"
            with self.store.get_connection() as conn:
                rows = conn.execute(
                    "SELECT category, content FROM memories ORDER BY timestamp DESC LIMIT 4"
                ).fetchall()
                long_term_hits = [dict(r) for r in rows]

        long_term_lines = [f"- [{m.get('category', 'general')}] {m.get('content', '')}" for m in long_term_hits]
        markdown_tail = self.recall_tail(max_chars=2400) if self.should_refresh_pools(user_text, active_history) else self.recall_tail(max_chars=1200)

        sections = []
        if short_term_lines:
            sections.append("[Short-Term Memory Pool (Recent Session Activity)]\n" + "\n".join(short_term_lines))
        if long_term_lines:
            sections.append("[Long-Term Memory Pool (Episodic DB)]\n" + "\n".join(long_term_lines))
        if markdown_tail:
            sections.append("[Long-Term Memory Pool (Compacted Markdown)]\n" + markdown_tail)

        return {
            "short_term_count": len(short_term_lines),
            "long_term_count": len(long_term_lines),
            "refreshed": bool(sections),
            "formatted_context": "\n\n".join(sections),
        }

    # ------------------------------------------------------------------
    # Pool 2: Rollover & Automatic Maintenance
    # ------------------------------------------------------------------
    def rollover_if_needed(
        self,
        history: List[Dict[str, Any]],
        prompt_tokens: int = 0,
    ) -> List[Dict[str, Any]]:
        token_trigger = prompt_tokens >= config.MAX_CONTEXT_TOKENS * config.CONTEXT_ROLLOVER_RATIO
        length_trigger = len(history) > self.short_term_max_messages
        if not (token_trigger or length_trigger):
            self.save_short_term_pool(history)
            return history
        if len(history) < 2:
            self.save_short_term_pool(history)
            return history

        cut = max(1, int(len(history) * config.CONTEXT_ROLLOVER_FRACTION))
        moved = history[:cut]
        remaining = history[cut:]
        self._append_markdown("Context rollover", moved)
        self.store.add_memory(
            f"Context rollover moved {cut} messages to {self.path} at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            category="context_rollover",
            importance=7.0,
        )
        self.save_short_term_pool(remaining)
        return remaining

    def auto_maintain_pools(
        self,
        user_text: str,
        assistant_text: str,
        history: List[Dict[str, Any]],
        prompt_tokens: int = 0,
        summarizer: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Post-turn deterministic helper: updates Short-Term Pool, rolls overflow
        into Long-Term Pool, records episodic summary, and compacts Long-Term Markdown if needed.
        """
        updated_history = self.rollover_if_needed(history, prompt_tokens=prompt_tokens)
        self.save_short_term_pool(updated_history)
        if user_text and assistant_text:
            self.store.add_memory(
                f"User asked: {user_text[:200]}. Nova responded: {assistant_text[:200]}",
                category="conversation",
                importance=6.0 if len(assistant_text) > 120 else 5.0,
            )
        if summarizer is not None:
            try:
                self.maybe_compact(summarizer)
            except Exception:
                self.maybe_compact(self._deterministic_fallback_summarize)
        return updated_history

    @staticmethod
    def _deterministic_fallback_summarize(source: str) -> str:
        """Zero-token deterministic fallback compactor when LLM is offline/busy."""
        lines = [ln.strip() for ln in source.splitlines() if ln.strip() and not ln.startswith("_Compacted")]
        seen = []
        for ln in lines[-40:]:
            if ln not in seen:
                seen.append(ln)
        return "\n".join(seen[-25:])

    def recall_tail(self, max_chars: int = 3800) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8", errors="replace")[-max_chars:]

    def maybe_compact(self, summarize: Callable[[str], str]) -> bool:
        if not self.path.exists():
            return False
        stat = self.path.stat()
        due_to_size = stat.st_size > config.MEMORY_COMPACTION_MAX_CHARS
        due_to_time = time.time() - stat.st_mtime >= config.MEMORY_COMPACTION_INTERVAL_SECONDS
        if not (due_to_size or due_to_time):
            return False

        source = self.path.read_text(encoding="utf-8", errors="replace")
        summary = summarize(source[: config.MEMORY_COMPACTION_MAX_CHARS * 2]).strip()
        if not summary:
            return False
        self.path.write_text(
            "# DeepClaw Long-Term Memory\n\n"
            f"_Compacted {time.strftime('%Y-%m-%d %H:%M:%S')}; source retained in SQLite traces._\n\n"
            f"{summary}\n",
            encoding="utf-8",
        )
        return True

    def _append_markdown(self, title: str, messages: List[Dict[str, Any]]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n## {title} — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for message in messages:
                role = message.get("role", "unknown").title()
                content = str(message.get("content", "")).strip()
                if content:
                    stream.write(f"**{role}:**\n\n{content}\n\n")
