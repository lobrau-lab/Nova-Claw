#!/usr/bin/env python3
"""
Nova-Claw - OMP, Hermes, Desktop Bridge, Plugin & Application Takeover Skill Suite
Equips the resident model with the full set of OMP + Hermes tools, Desktop note helpers,
Windows Desktop SSH bridge, Plugin Installer, Static Decision Router helpers, and Advisory Playbooks.
"""

import ast
import csv
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import config
from core.workspace import validate_workspace_path
from core.static_router import StaticDecisionRouter, save_note_to_desktop
from control.macos_bridge import ComputerController
from skills.registry import Skill, SkillRegistry


DESKTOP_HOST = os.getenv("NOVA_WINDOWS_DESKTOP_HOST", "load@DESKTOP-HMGN413")


def handle_save_note(title: str, content: str, subfolder: str = "", extension: str = ".md") -> str:
    """Built-in helper: creates a folder on the Desktop (~/Desktop/DeepClaw_Notes) and saves notes/text."""
    path = save_note_to_desktop(title=title, content=content, subfolder=subfolder, extension=extension)
    return f"Saved note to Desktop folder: {path} ({len(content)} chars)"


def handle_run_on_desktop(command: str, timeout: int = 30) -> str:
    """Runs a shell command on the Windows desktop (DESKTOP-HMGN413) over passwordless SSH."""
    if not command or not command.strip():
        return "Error: command is required."
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", DESKTOP_HOST, command],
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 300)),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"[Desktop SSH Exit {proc.returncode}] {err or out}"
        return out or "[Desktop command completed with no output]"
    except Exception as exc:
        return f"Error running command on desktop ({DESKTOP_HOST}): {exc}"


def handle_desktop_file(action: str, remote_path: str, local_path: str = "") -> str:
    """Reads or copies files between this Mac and the Windows desktop over SSH/SCP."""
    act = (action or "").strip().lower()
    if act == "read":
        return handle_run_on_desktop(f'type "{remote_path}"')
    if not local_path:
        return "Error: local_path is required for copy_to and copy_from."
    norm_remote = remote_path.replace("\\", "/")
    try:
        if act == "copy_to":
            src = validate_workspace_path(Path(local_path).expanduser(), operation="read")
            cmd = ["scp", "-o", "BatchMode=yes", str(src), f"{DESKTOP_HOST}:{norm_remote}"]
        elif act == "copy_from":
            dst = validate_workspace_path(Path(local_path).expanduser(), operation="write")
            dst.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["scp", "-o", "BatchMode=yes", f"{DESKTOP_HOST}:{norm_remote}", str(dst)]
        else:
            return "Error: action must be read, copy_to, or copy_from."
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return f"Error in desktop_file ({act}): {proc.stderr.strip()}"
        return f"Successfully executed desktop_file {act} ({remote_path} <-> {local_path})."
    except Exception as exc:
        return f"Error in desktop_file: {exc}"


def handle_git_ops(action: str, path: str = ".", args: str = "") -> str:
    """OMP/Hermes Git helper: status, diff, log, branch, commit with deterministic safety checks."""
    workdir = validate_workspace_path(Path(path).expanduser(), operation="git")
    act = (action or "status").strip().lower()
    if act == "status":
        cmd = ["git", "status", "--short", "--branch"]
    elif act == "diff":
        cmd = ["git", "diff", "--stat"] if not args else ["git", "diff", args]
    elif act == "log":
        cmd = ["git", "log", "-n", "10", "--oneline"]
    elif act == "branch":
        cmd = ["git", "branch", "-a"]
    elif act == "commit":
        if not args.strip():
            return "Error: commit message required in 'args'."
        cmd = ["git", "commit", "-m", args.strip()]
    else:
        return f"Error: unsupported git action '{act}'."
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True, timeout=20)
        return (proc.stdout or proc.stderr or "[git ok]").strip()[:config.MAX_TOOL_OUTPUT_CHARS]
    except Exception as exc:
        return f"Error running git {act}: {exc}"


def handle_code_review(path: str) -> str:
    """OMP/Hermes AST & static code analyzer: checks syntax, line count, functions, classes, and issues."""
    target = validate_workspace_path(Path(path).expanduser(), operation="read")
    if not target.is_file():
        return f"Error: File not found: {target}"
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if target.suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(target))
            funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            return (
                f"Code Review OK: {target.name} ({len(lines)} lines, "
                f"{len(classes)} classes: {classes[:10]}, {len(funcs)} functions: {funcs[:15]})."
            )
        except SyntaxError as exc:
            return f"SyntaxError in {target.name} at line {exc.lineno}: {exc.msg}"
    return f"Inspected {target.name}: {len(lines)} lines, {len(text)} chars."


def handle_spreadsheet_ops(path: str, group_by: str = "", sum_column: str = "") -> str:
    """OMP/Hermes tabular CSV analyzer: computes row counts, status segmentations, and numeric sums."""
    target = validate_workspace_path(Path(path).expanduser(), operation="read")
    if not target.is_file():
        return f"Error: CSV file not found: {target}"
    with target.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    total_rows = len(rows)
    segments: Dict[str, int] = {}
    numeric_sum = 0.0
    for r in rows:
        if group_by and group_by in r:
            key = str(r[group_by]).strip() or "(empty)"
            segments[key] = segments.get(key, 0) + 1
        if sum_column and sum_column in r:
            try:
                numeric_sum += float(str(r[sum_column]).replace(",", "").replace("$", "").strip())
            except ValueError:
                pass
    summary = {
        "file": str(target),
        "total_rows": total_rows,
        "group_by": group_by or None,
        "segmentation": segments,
        "sum_column": sum_column or None,
        "sum_total": round(numeric_sum, 4) if sum_column else None,
    }
    return json.dumps(summary, indent=2)


def handle_manage_plugins(
    action: str,
    name: str = "",
    source_path: str = "",
    registry: Optional[SkillRegistry] = None,
) -> str:
    """Installs, lists, or loads plugins and external skills into Nova-Claw."""
    act = (action or "list").strip().lower()
    config.PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    config.SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if act == "list":
        installed_plugins = [p.name for p in sorted(config.PLUGINS_DIR.glob("*")) if not p.name.startswith(".")]
        installed_skills = [p.stem for p in sorted(config.SKILLS_DIR.glob("*.py")) if not p.name.startswith("_")]
        agent_skills = []
        agent_skills_root = Path(__file__).resolve().parent.parent / ".agents" / "skills"
        if agent_skills_root.is_dir():
            agent_skills = [d.name for d in sorted(agent_skills_root.iterdir()) if d.is_dir()]
        return json.dumps({
            "plugins_dir": str(config.PLUGINS_DIR),
            "installed_plugins": installed_plugins,
            "dynamic_skills": installed_skills,
            "omp_hermes_agent_skills": agent_skills,
        }, indent=2)

    if act == "install":
        if not source_path:
            return "Error: source_path is required to install a plugin."
        src = validate_workspace_path(Path(source_path).expanduser(), operation="read")
        if not src.exists():
            return f"Error: plugin source '{src}' does not exist."
        dest_name = re.sub(r"[^a-zA-Z0-9._-]", "_", name or src.name)
        if src.is_file() and src.suffix == ".py":
            dest = config.SKILLS_DIR / (dest_name if dest_name.endswith(".py") else f"{dest_name}.py")
            shutil.copy2(src, dest)
            loaded = registry.load_skill_file(dest) if registry else False
            return f"Installed Python skill plugin to {dest} (hot-loaded={loaded})."
        dest = config.PLUGINS_DIR / dest_name
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        return f"Installed plugin '{dest_name}' into {dest}."

    return f"Error: unsupported plugin action '{act}'. Use list or install."


def handle_use_skill_playbook(skill_name: str, input_text: str = "") -> str:
    """Loads and applies any installed OMP / Hermes / User SKILL.md playbook on this device."""
    clean = re.sub(r"^(?:user:|system:)", "", (skill_name or "").strip().lower())
    skills_root = Path(__file__).resolve().parent.parent / ".agents" / "skills"
    candidates = {}
    if skills_root.is_dir():
        for d in skills_root.iterdir():
            if d.is_dir() and (d / "SKILL.md").is_file():
                candidates[d.name.lower()] = d / "SKILL.md"
    if clean in ("list", "all", ""):
        return json.dumps({"available_playbooks": sorted(candidates.keys())}, indent=2)
    matched = candidates.get(clean)
    if not matched:
        for k, v in candidates.items():
            if clean in k or k in clean:
                matched = v
                break
    if not matched:
        return f"Error: Skill playbook '{skill_name}' not found. Available: {sorted(candidates.keys())}"
    body = matched.read_text(encoding="utf-8", errors="replace")[:3500]
    if input_text:
        return f"[Skill Playbook: {matched.parent.name}]\n{body}\n\n[Target Input]:\n{input_text}"
    return f"[Skill Playbook: {matched.parent.name}]\n{body}"


def register_omp_hermes_skills(
    registry: SkillRegistry,
    controller: Optional[ComputerController] = None,
    static_router: Optional[StaticDecisionRouter] = None,
    approval: Optional[Callable[[str, str], bool]] = None,
) -> None:
    """Registers the full OMP + Hermes + Desktop Note + App Takeover + Static Helper tool suite."""
    ctrl = controller or ComputerController()
    router = static_router or StaticDecisionRouter()

    # 1. Desktop Note & Text Saver Helper
    registry.register(Skill(
        name="save_note",
        description=(
            "Creates and uses the dedicated folder on the Desktop (~/Desktop/DeepClaw_Notes) to store notes, "
            "saved text, memos, or summaries. Always use this tool when creating notes or saving text."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note filename or title"},
                "content": {"type": "string", "description": "Full text or Markdown content to save"},
                "subfolder": {"type": "string", "description": "Optional subfolder inside ~/Desktop/DeepClaw_Notes"},
                "extension": {"type": "string", "enum": [".md", ".txt", ".json", ".log"]},
            },
            "required": ["title", "content"],
        },
        handler=handle_save_note,
    ))

    # 2. Application Connect / Plug-Into / Takeover Tool
    registry.register(Skill(
        name="app_takeover",
        description=(
            "Connects to, plugs into, inspects, or takes over any macOS application (e.g. Safari, Finder, Xcode, "
            "Spotify, ComfyUI, Blender, Terminal) using AppleScript, JXA, System Events Accessibility UI inspection, "
            "menu automation, or local endpoint attachment."
        ),
        parameters={
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Target macOS application name"},
                "mode": {
                    "type": "string",
                    "enum": ["takeover", "connect", "plug_in", "inspect", "menu", "applescript", "jxa"],
                    "description": "Operation mode (default: takeover)",
                },
                "command": {"type": "string", "description": "Optional text to type, AppleScript body, or JXA code"},
                "menu_bar_item": {"type": "string", "description": "Top-level menu bar name when mode='menu' (e.g. 'File')"},
                "menu_item": {"type": "string", "description": "Menu item name when mode='menu' (e.g. 'New Window')"},
                "endpoint_url": {"type": "string", "description": "Optional local port/URL when plugging into an app server"},
            },
            "required": ["app_name"],
        },
        handler=lambda app_name, mode="takeover", command="", menu_bar_item="", menu_item="", endpoint_url="": (
            "Error: macOS app control requires interactive approval."
            if approval and not approval(f"app_takeover:{mode}", f"{app_name} {command}")
            else ctrl.inspect_app_ui(app_name)
            if mode == "inspect"
            else ctrl.connect_or_takeover_app(
                app_name=app_name,
                mode=mode,
                command=command,
                menu_path=[menu_bar_item, menu_item] if (menu_bar_item and menu_item) else None,
                endpoint_url=endpoint_url,
            )
        ),
    ))

    # 3. Plugin Manager Tool
    registry.register(Skill(
        name="manage_plugins",
        description="Lists or installs plugins and external skills into Nova-Claw.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "install"]},
                "name": {"type": "string", "description": "Plugin name when installing"},
                "source_path": {"type": "string", "description": "Local file or directory path to install"},
            },
            "required": ["action"],
        },
        handler=lambda action, name="", source_path="": handle_manage_plugins(
            action=action, name=name, source_path=source_path, registry=registry
        ),
    ))

    # 4. Static Decision Router Helper Tool (Compute Saver)
    registry.register(Skill(
        name="manage_static_rules",
        description=(
            "Evaluates or registers deterministic if-condition rules in the StaticDecisionRouter "
            "to bypass LLM inference for unchanging project decisions and save compute."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["evaluate", "add_rule", "list_rules"]},
                "query_or_rule_id": {"type": "string", "description": "Prompt to evaluate or unique rule_id to add"},
                "category": {"type": "string", "description": "Rule category (e.g. video_specs, storage_policy)"},
                "keywords_csv": {"type": "string", "description": "Comma-separated trigger keywords when adding a rule"},
                "value": {"type": "string", "description": "Locked deterministic value when adding a rule"},
                "explanation": {"type": "string", "description": "Explanation for the static rule"},
            },
            "required": ["action"],
        },
        handler=lambda action, query_or_rule_id="", category="general", keywords_csv="", value="", explanation="": (
            json.dumps(router.rules, indent=2)
            if action == "list_rules"
            else json.dumps(router.evaluate(query_or_rule_id, category=category if category != "general" else None), indent=2)
            if action == "evaluate"
            else json.dumps(
                router.add_decision_rule(
                    rule_id=query_or_rule_id or f"rule_{int(time.time())}",
                    category=category,
                    keywords=[k.strip() for k in keywords_csv.split(",") if k.strip()],
                    value=value,
                    explanation=explanation or value,
                ),
                indent=2,
            )
        ),
    ))

    # 5. Windows Desktop Bridge Tools (run_on_desktop & desktop_file)
    registry.register(Skill(
        name="run_on_desktop",
        description="Runs a shell command on the Windows desktop rig (DESKTOP-HMGN413) over passwordless SSH.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute on DESKTOP-HMGN413"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
            },
            "required": ["command"],
        },
        handler=handle_run_on_desktop,
    ))

    registry.register(Skill(
        name="desktop_file",
        description="Reads or copies files to and from the Windows desktop rig (DESKTOP-HMGN413) over SSH/SCP.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "copy_to", "copy_from"]},
                "remote_path": {"type": "string", "description": "Windows path on DESKTOP-HMGN413"},
                "local_path": {"type": "string", "description": "Local Mac path inside approved workspaces"},
            },
            "required": ["action", "remote_path"],
        },
        handler=handle_desktop_file,
    ))

    # 6. OMP & Hermes Core Developer & Analyst Skills (git_ops, code_review, spreadsheet_ops, skill_playbook)
    registry.register(Skill(
        name="git_ops",
        description="Executes structured Git operations (status, diff, log, branch, commit) inside an approved workspace.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "diff", "log", "branch", "commit"]},
                "path": {"type": "string", "description": "Repository directory (default: '.')"},
                "args": {"type": "string", "description": "Optional diff target or commit message"},
            },
            "required": ["action"],
        },
        handler=handle_git_ops,
    ))

    registry.register(Skill(
        name="code_review",
        description="Performs AST syntax validation and structural summary of a source file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path inside approved workspace"},
            },
            "required": ["path"],
        },
        handler=handle_code_review,
    ))

    registry.register(Skill(
        name="spreadsheet_ops",
        description="Analyzes a CSV spreadsheet with row counts, status segmentation, and column summation.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "CSV file path inside approved workspace"},
                "group_by": {"type": "string", "description": "Optional column name for count segmentation"},
                "sum_column": {"type": "string", "description": "Optional numeric column name to sum"},
            },
            "required": ["path"],
        },
        handler=handle_spreadsheet_ops,
    ))

    registry.register(Skill(
        name="use_skill_playbook",
        description=(
            "Loads any installed OMP, Hermes, or User skill playbook on this device "
            "(ponytail, static-decision-router, focus-your-energy, generate-fresh-ideas, "
            "get-more-perspectives, ltx-video-prompt-architect, match-my-writing-style, "
            "agent-creation-and-delegation)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Name of the skill playbook (or 'list' to see all)"},
                "input_text": {"type": "string", "description": "Optional context or input to apply the skill to"},
            },
            "required": ["skill_name"],
        },
        handler=handle_use_skill_playbook,
    ))
