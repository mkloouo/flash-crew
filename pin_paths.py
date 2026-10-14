#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Rewrite the installed flash-crew hooks.json to use absolute paths.

Antigravity sanitizes the hook environment, and a hook that fails to start
blocks the tool call. If `uv` isn't on the hook's PATH, or hooks don't run
from the plugin folder, every subagent spawn gets blocked with
"pre-tool hook failed". Running this once after install pins the absolute
path of uv and of the gate script, which removes both risks.

Usage: uv run pin_paths.py [installed-plugin-dir]
Default dir: ~/.gemini/config/plugins/flash-crew (or ~/.gemini/antigravity-cli/plugins/flash-crew)
"""
import json
import shutil
import sys
from pathlib import Path

def find_target() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    candidates = [
        Path.home() / ".gemini" / "config" / "plugins" / "flash-crew",
        Path.home() / ".gemini" / "antigravity-cli" / "plugins" / "flash-crew",
    ]
    for c in candidates:
        if (c / "hooks.json").is_file() and (c / "hooks" / "agent_gate.py").is_file():
            return c.resolve()
    # If not installed yet, check if run from the plugin repository
    cwd = Path.cwd().resolve()
    if (cwd / "hooks.json").is_file() and (cwd / "hooks" / "agent_gate.py").is_file():
        return cwd
    # Default to standard config location for clear error reporting
    return candidates[0].resolve()

target = find_target()
hooks_file = target / "hooks.json"
gate = target / "hooks" / "agent_gate.py"
uv = shutil.which("uv")
python3 = shutil.which("python3") or sys.executable

if not hooks_file.is_file() or not gate.is_file():
    sys.exit(f"Not a flash-crew plugin folder: {target}\nIf you haven't installed it yet, run: agy plugin install .")

hooks = json.loads(hooks_file.read_text())
if uv:
    command = f'"{uv}" run --quiet --script "{gate}"'
else:
    command = f'"{python3}" "{gate}"'
for group in hooks["flash-crew-gate"]["PreToolUse"]:
    for h in group["hooks"]:
        h["command"] = command
hooks_file.write_text(json.dumps(hooks, indent=2) + "\n")
print(f"Target: {target}")
print(f"Pinned hook command:\n  {command}\nRestart agy (or reload plugins) to apply.")
