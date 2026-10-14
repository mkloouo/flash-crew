#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""PreToolUse gate for Antigravity CLI subagent tools.

Denies the subagent spawns that silently run on the main agent's model:
  - define_subagent (ad-hoc agents have no model tier of their own)
  - the built-in `self` subagent (a clone of the caller)
  - file-defined agents whose `model` is `inherit` or missing
Everything else (crew-* workers, agents with model flash/pro, built-ins
like research/browser) is allowed. Every call is logged.

Antigravity treats a crashed, timed-out or non-zero hook as a block, so
this script always exits 0 and allows the call if anything goes wrong
inside it. Settings live in gate.json because the hook environment is
sanitized and custom env vars don't reach it.
"""
import json
import re
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
HOME = Path.home()
LOG = HOME / ".gemini" / "antigravity-cli" / "flash-crew-logs" / "delegations.jsonl"

WORKERS = "crew-scout (search), crew-runner (tests/lint/build), crew-implementer (scoped edit), crew-checker (verify)"


def load_config():
    cfg = {"blockDefineSubagent": True, "blockSelf": True, "allowInheritModel": []}
    try:
        cfg.update(json.loads((PLUGIN_DIR / "gate.json").read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def agent_dirs(workspaces):
    dirs = [PLUGIN_DIR / "agents", HOME / ".gemini" / "config" / "agents"]
    for plugins in (HOME / ".gemini" / "antigravity-cli" / "plugins",
                    HOME / ".gemini" / "config" / "plugins"):
        if plugins.is_dir():
            dirs += [p / "agents" for p in plugins.iterdir()]
    for ws in workspaces or []:
        dirs.append(Path(ws) / ".agents" / "agents")
        if (Path(ws) / ".agents" / "plugins").is_dir():
            dirs += [p / "agents" for p in (Path(ws) / ".agents" / "plugins").iterdir()]
    return [d for d in dirs if d.is_dir()]


def frontmatter(path):
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "\t", "-")):
            fields[k.strip()] = v.strip().strip("'\"")
    return fields


def find_model(type_name, workspaces):
    """Return the model field of the agent named type_name, '' if unset,
    or None if no definition file was found (built-in or dynamic agent)."""
    for d in agent_dirs(workspaces):
        for f in list(d.glob("*.md")) + list(d.glob("*/agent.md")):
            fm = frontmatter(f)
            name = fm.get("name") or (f.parent.name if f.name == "agent.md" else f.stem)
            if name == type_name:
                return fm.get("model", "").lower()
    return None


def subagent_types(args):
    subs = args.get("Subagents") or args.get("subagents") or []
    if isinstance(subs, dict):
        subs = [subs]
    names = []
    for s in subs if isinstance(subs, list) else []:
        if isinstance(s, dict):
            t = s.get("TypeName") or s.get("typeName") or s.get("type_name") or ""
            names.append(str(t).strip())
    return names


def decide(event, cfg):
    call = event.get("toolCall") or {}
    tool = call.get("name") or ""
    args = call.get("args") or {}
    workspaces = event.get("workspacePaths") or []

    if tool == "define_subagent":
        if cfg.get("blockDefineSubagent", True):
            return "deny", (
                "flash-crew: agents made with define_subagent run on the main agent's model. "
                f"Use a predefined worker instead: {WORKERS}. Put the task details in the Prompt."
            ), []
        return "allow", "", []

    if tool != "invoke_subagent":
        return "allow", "", []

    allowed_inherit = set(cfg.get("allowInheritModel") or [])
    types = subagent_types(args)
    for t in types:
        base = t.split(":")[-1]
        if base.lower() == "self" and cfg.get("blockSelf", True):
            return "deny", (
                "flash-crew: the 'self' subagent clones the main agent and its model. "
                f"Use a worker instead: {WORKERS}."
            ), types
        model = find_model(base, workspaces)
        if model is not None and model in ("", "inherit") and base not in allowed_inherit:
            return "deny", (
                f"flash-crew: agent '{base}' has no model tier (inherit), so it runs on the main "
                f"model. Use a worker ({WORKERS}), set `model: flash` or `model: pro` in its "
                "definition, or add it to allowInheritModel in the flash-crew gate.json."
            ), types
    return "allow", "", types


def main():
    decision, reason, types = "allow", "", []
    event = {}
    try:
        event = json.loads(sys.stdin.read() or "{}")
        decision, reason, types = decide(event, load_config())
    except Exception as e:  # never block on our own bug
        decision, reason = "allow", ""
        types = [f"(gate error: {type(e).__name__})"]

    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "conversation": event.get("conversationId"),
                "mainModel": event.get("modelName"),
                "tool": (event.get("toolCall") or {}).get("name"),
                "types": types,
                "decision": decision,
            }) + "\n")
    except Exception:
        pass

    out = {"decision": decision}
    if reason:
        out["reason"] = reason
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
