#!/usr/bin/env python3
"""Generate a per-user LaunchAgent for the current Nova checkout and Python."""

import argparse
import os
import plistlib
import shlex
import sys
from pathlib import Path
from typing import Optional


LABEL = "com.deepclaw.nova"


def build_agent_plist(python_executable: Path, project_root: Path, log_dir: Path) -> dict:
    python_executable = Path(python_executable).resolve()
    project_root = Path(project_root).resolve()
    log_dir = Path(log_dir).resolve()
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python_executable), str(project_root / "nova.py"), "live"],
        "WorkingDirectory": str(project_root),
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Interactive",
        "Umask": "077",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(log_dir / "nova.out.log"),
        "StandardErrorPath": str(log_dir / "nova.err.log"),
    }


def write_agent_plist(
    output_path: Path,
    python_executable: Path,
    project_root: Path,
    log_dir: Optional[Path] = None,
) -> Path:
    output_path = Path(output_path).expanduser()
    log_dir = log_dir or (Path.home() / ".deepclaw" / "logs")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        plistlib.dump(build_agent_plist(python_executable, project_root, log_dir), stream)
    output_path.chmod(0o600)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Nova's per-user LaunchAgent plist")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python executable to run Nova")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        help="Output plist path (it is written but not loaded)",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    if not args.python.is_file() or not (project_root / "nova.py").is_file():
        parser.error("the Python executable and this checkout's nova.py must exist")
    output = write_agent_plist(args.output, args.python, project_root)
    print(f"Wrote {output}")
    print(f"Load when ready: launchctl bootstrap gui/{os.getuid()} {shlex.quote(str(output))}")


if __name__ == "__main__":
    main()
