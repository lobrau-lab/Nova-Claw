#!/usr/bin/env python3
"""
DeepClaw Nova - Full macOS Computer Control & Application Takeover Bridge
Gives Nova voice-directed and agentic control over macOS applications using
AppleScript, JXA, System Events Accessibility inspection, menu/window automation,
and local plugin/socket attachment.
"""

import sys
import subprocess
import time
import json
import re
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
import config


def _escape_applescript_string(value: str) -> str:
    """Escape data embedded in an AppleScript string literal."""
    return (str(value)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n"))


def _app_name(value: str) -> Optional[str]:
    # +5% stricter validation: max 120 chars (down from 128), strict safe charset
    name = str(value).strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+()'-]{0,119}", name):
        return None
    return name


def run_applescript(script: str, timeout: float = 9.5) -> Tuple[bool, str]:
    """Executes an AppleScript snippet via osascript (timeout tightened by 5% to 9.5s)."""
    if sys.platform != "darwin":
        return True, f"[Simulated macOS AppleScript: {script.strip()}]"

    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "AppleScript command timed out."
    except Exception as e:
        return False, str(e)


def run_jxa(script: str, timeout: float = 9.5) -> Tuple[bool, str]:
    """Executes a JavaScript for Automation (JXA) script on macOS."""
    if sys.platform != "darwin":
        return True, f"[Simulated macOS JXA: {script.strip()}]"
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "JXA command timed out."
    except Exception as e:
        return False, str(e)


class ComputerController:
    def __init__(self):
        self.connected_apps: Dict[str, Dict[str, Any]] = {}

    def open_app(self, app_name: str) -> str:
        """Launches or brings an application to the foreground."""
        safe_name = _app_name(app_name)
        if safe_name is None:
            return "Error: invalid application name."
        script = f'tell application "{_escape_applescript_string(safe_name)}" to activate'
        ok, res = run_applescript(script)
        if ok:
            return f"Activated {safe_name}."
        try:
            subprocess.run(["open", "-a", safe_name], check=True, timeout=5)
            return f"Opened {safe_name} via open launcher."
        except Exception as e:
            return f"Failed to open {app_name}: {e}"

    def quit_app(self, app_name: str) -> str:
        """Gracefully quits an application."""
        safe_name = _app_name(app_name)
        if safe_name is None:
            return "Error: invalid application name."
        script = f'tell application "{_escape_applescript_string(safe_name)}" to quit'
        ok, res = run_applescript(script)
        return f"Quit {safe_name}." if ok else f"Could not quit {safe_name}: {res}"

    def set_system_volume(self, percent: int) -> str:
        """Sets the system speaker volume (0 to 100)."""
        clamped = max(0, min(100, int(percent)))
        script = f"set volume output volume {clamped}"
        ok, res = run_applescript(script)
        return f"Volume set to {clamped}%." if ok else f"Error setting volume: {res}"

    def media_control(self, action: str) -> str:
        """Controls media playback ('play', 'pause', 'next', 'previous', 'stop')."""
        actions = {
            "play": "play",
            "pause": "pause",
            "next": "next track",
            "previous": "previous track",
            "stop": "pause",
        }
        mapped = actions.get(action.lower().strip())
        if mapped is None:
            return "Unsupported media action. Use play, pause, next, previous, or stop."
        script = f"""
        if application "Spotify" is running then
            tell application "Spotify" to {mapped}
        else if application "Music" is running then
            tell application "Music" to {mapped}
        else
            tell application "System Events" to key code 49 -- space toggle
        end if
        """
        ok, res = run_applescript(script)
        return f"Executed media {mapped}." if ok else f"Media control error: {res}"

    def type_text(self, text: str) -> str:
        """Types text into the currently active macOS window."""
        escaped = _escape_applescript_string(text)
        script = f'tell application "System Events" to keystroke "{escaped}"'
        ok, res = run_applescript(script)
        return "Typed text successfully." if ok else f"Keystroke error: {res}"

    def press_key_combo(self, key: str, modifiers: Optional[List[str]] = None) -> str:
        """Presses key combinations (e.g. key='c', modifiers=['command down'])."""
        allowed_mods = {"command down", "shift down", "option down", "control down"}
        safe_mods = [m for m in (modifiers or []) if m in allowed_mods]
        mod_str = " using {" + ", ".join(safe_mods) + "}" if safe_mods else ""
        escaped_key = _escape_applescript_string(key[:1] if key else "")
        script = f'tell application "System Events" to keystroke "{escaped_key}"{mod_str}'
        ok, res = run_applescript(script)
        return f"Pressed '{escaped_key}'{mod_str}." if ok else f"Key combo error: {res}"

    def show_notification(self, title: str, message: str) -> str:
        """Displays a native macOS banner notification."""
        script = (f'display notification "{_escape_applescript_string(message)}" '
                  f'with title "{_escape_applescript_string(title)}" sound name "Glass"')
        ok, res = run_applescript(script)
        return "Notification displayed." if ok else f"Notification error: {res}"

    def take_screenshot(self, output_path: Optional[str] = None) -> str:
        """Captures the current macOS screen."""
        target = output_path or f"/tmp/screenshot_{int(time.time())}.png"
        if sys.platform == "darwin":
            try:
                subprocess.run(["screencapture", "-x", target], check=True, timeout=5)
                return f"Screenshot saved to {target}"
            except Exception as e:
                return f"Failed to capture screen: {e}"
        return f"[Simulated screenshot saved to {target}]"

    # ------------------------------------------------------------------
    # Application Connect / Plug-Into / Takeover Capabilities
    # ------------------------------------------------------------------
    def connect_or_takeover_app(
        self,
        app_name: str,
        mode: str = "takeover",
        command: str = "",
        menu_path: Optional[List[str]] = None,
        endpoint_url: Optional[str] = None,
    ) -> str:
        """
        Connects to, plugs into, or takes over a target macOS application:
        - 'connect' / 'plug_in': attaches to the app, inspects its windows/menus/ports, and registers an active bridge.
        - 'takeover' / 'focus': activates the app, inspects its UI hierarchy (windows, menus, buttons), and optionally runs an action.
        - 'menu': triggers a specific menu bar path (e.g. ['File', 'New Window']).
        - 'applescript' / 'jxa': executes a scoped automation command inside the application context.
        """
        safe_name = _app_name(app_name)
        if safe_name is None:
            return "Error: invalid application name for takeover/connection."

        escaped_app = _escape_applescript_string(safe_name)
        mode_clean = (mode or "takeover").strip().lower()

        if mode_clean == "menu" and menu_path and len(menu_path) >= 2:
            menu_bar_item = _escape_applescript_string(menu_path[0])
            menu_item = _escape_applescript_string(menu_path[1])
            script = f'''
            tell application "{escaped_app}" to activate
            tell application "System Events"
                tell process "{escaped_app}"
                    click menu item "{menu_item}" of menu 1 of menu bar item "{menu_bar_item}" of menu bar 1
                end tell
            end tell
            '''
            ok, res = run_applescript(script)
            return f"Clicked menu {' > '.join(menu_path)} in {safe_name}." if ok else f"Menu action failed in {safe_name}: {res}"

        if mode_clean == "applescript" and command:
            script = f'tell application "{escaped_app}"\n{command}\nend tell'
            ok, res = run_applescript(script)
            return f"[{safe_name} AppleScript Result]: {res or 'OK'}" if ok else f"Error controlling {safe_name}: {res}"

        if mode_clean == "jxa" and command:
            jxa_code = f'const app = Application("{escaped_app}"); app.includeStandardAdditions = true; {command}'
            ok, res = run_jxa(jxa_code)
            return f"[{safe_name} JXA Result]: {res or 'OK'}" if ok else f"Error in JXA bridge for {safe_name}: {res}"

        # Default: connect / plug_in / takeover + inspect UI hierarchy
        self.open_app(safe_name)
        ui_info = self.inspect_app_ui(safe_name)
        bridge_record = {
            "app_name": safe_name,
            "mode": mode_clean,
            "endpoint_url": endpoint_url or "",
            "connected_at": time.time(),
            "ui_snapshot": ui_info,
        }
        self.connected_apps[safe_name.lower()] = bridge_record

        if command:
            # Type or execute the follow-up command if requested during takeover
            self.type_text(command)
            return (
                f"Connected and took over '{safe_name}' (mode={mode_clean}). "
                f"Sent input '{command[:60]}'. UI Snapshot: {ui_info}"
            )

        return (
            f"Connected and plugged into '{safe_name}' (mode={mode_clean}). "
            f"Active bridge registered. UI Snapshot: {ui_info}"
        )

    def inspect_app_ui(self, app_name: str) -> str:
        """Inspects windows, menus, and frontmost UI elements of a target macOS app."""
        safe_name = _app_name(app_name)
        if safe_name is None:
            return "Error: invalid application name."
        escaped = _escape_applescript_string(safe_name)
        script = f'''
        tell application "System Events"
            if exists process "{escaped}" then
                tell process "{escaped}"
                    set winNames to name of every window
                    set menuNames to name of every menu bar item of menu bar 1
                    return "Windows: " & (winNames as string) & " | Menus: " & (menuNames as string)
                end tell
            else
                return "Process not currently running in System Events."
            end if
        end tell
        '''
        ok, res = run_applescript(script)
        return res if ok and res else f"Process '{safe_name}' active (UI tree ready)."
