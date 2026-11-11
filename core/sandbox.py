#!/usr/bin/env python3
"""Native macOS Seatbelt policy generation for governed child processes."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, List


class SandboxUnavailableError(RuntimeError):
    """Raised when the required native process sandbox cannot be started."""


def _seatbelt_path(path: Path) -> str:
    value = str(path.resolve())
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class SandboxPolicy:
    """Deny-by-default policy for one governed command working directory."""

    SYSTEM_READ_ROOTS = (
        "/bin", "/usr", "/System", "/Library", "/Applications",
        "/private/var/db", "/private/var/folders", "/private/tmp",
        "/dev", "/opt/homebrew", "/opt/local",
    )

    def __init__(self, workdir: str | Path, read_roots: Iterable[str | Path] = (), allow_network: bool = False):
        self.workdir = Path(workdir).expanduser().resolve()
        self.read_roots = tuple(Path(root).expanduser().resolve() for root in read_roots)
        self.allow_network = allow_network

    def profile(self) -> str:
        lines = [
            "(version 1)",
            "(deny default)",
            "(allow process*)",
            "(allow sysctl-read)",
            "(allow file-read-metadata)",
        ]
        for root in (*self.SYSTEM_READ_ROOTS, *self.read_roots):
            lines.append(f"(allow file-read* (subpath {_seatbelt_path(Path(root))}))")
        lines.append(f"(allow file-read* (subpath {_seatbelt_path(self.workdir)}))")
        lines.append(f"(allow file-write* (subpath {_seatbelt_path(self.workdir)}))")
        lines.append('(allow file-write* (subpath "/private/tmp"))')
        if self.allow_network:
            lines.append("(allow network-outbound)")
        return "\n".join(lines) + "\n"

    def command_prefix(self) -> List[str]:
        if sys.platform != "darwin":
            raise SandboxUnavailableError("Native macOS Seatbelt sandbox is unavailable on this platform.")
        sandbox_exec = shutil.which("sandbox-exec")
        if not sandbox_exec:
            raise SandboxUnavailableError("sandbox-exec is unavailable; refusing unsandboxed execution.")
        return [sandbox_exec, "-p", self.profile()]


def sandbox_required() -> bool:
    default = "1" if sys.platform == "darwin" else "0"
    return os.getenv("NOVA_REQUIRE_OS_SANDBOX", default) == "1"
