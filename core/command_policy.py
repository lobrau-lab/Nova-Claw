"""Deterministic approval gates for high-impact shell commands."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDecision:
    allowed: bool
    category: str = "safe"
    reason: str = ""


_DESTRUCTIVE = re.compile(
    r"(?:\bsudo\b|\brm\s+(?:-[^\s]*[rf][^\s]*\s+|--(?:recursive|force)\b)|"
    r"\b(?:mkfs|diskutil\s+eraseDisk|shutdown|reboot|halt)\b)",
    re.IGNORECASE,
)
_EXTERNAL = re.compile(
    r"(?:\b(?:curl|wget|ssh|scp|nc|osascript)\b|\bgit\s+push\b|\bopen\s+-[a-z])",
    re.IGNORECASE,
)


def inspect_command(command: str) -> CommandDecision:
    """Require explicit environment approval for destructive/external commands."""
    text = str(command or "")
    if _DESTRUCTIVE.search(text) and os.getenv("NOVA_ALLOW_DESTRUCTIVE_COMMANDS") != "1":
        return CommandDecision(False, "COMMAND_APPROVAL_REQUIRED", "destructive command requires NOVA_ALLOW_DESTRUCTIVE_COMMANDS=1")
    if _EXTERNAL.search(text) and os.getenv("NOVA_ALLOW_EXTERNAL_COMMANDS") != "1":
        return CommandDecision(False, "COMMAND_APPROVAL_REQUIRED", "external command requires NOVA_ALLOW_EXTERNAL_COMMANDS=1")
    return CommandDecision(True)
