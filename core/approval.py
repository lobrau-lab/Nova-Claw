"""Interactive approval gate for privileged macOS automation actions."""

from __future__ import annotations

import sys
from typing import Callable, Optional


class ApprovalGate:
    def __init__(self, interactive: Optional[bool] = None, input_fn: Callable[[str], str] = input):
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.input_fn = input_fn

    def approve(self, action: str, details: str = "") -> bool:
        if not self.interactive:
            return False
        summary = " ".join(str(details).split())[:300]
        try:
            answer = self.input_fn(f"Approve macOS action '{action}' ({summary})? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() in {"y", "yes"}
