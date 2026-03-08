"""
One-off migration: update old session JSON result strings to match
the new Place return format.

Changes:
- create success: "You create {name}. {desc}" → "{name} is here. {desc}"
- venture success: "You have ventured to {name}. {desc}" → "You are now at {name}. {desc}"
- take success: "You take {what}. It is with you now." → "{what} is with you now."
- alter rename+desc: strips redundant "{what} is different now. " prefix when rename present
- drop success: "You release {what}. It is here now." → can't patch (need location)

go success (description added) and alter (description echo) are additive
changes that can't be retroactively applied — the old Place didn't return
that information. Old sessions keep their original result text for those.

Run from the palimpsest root:
    python scripts/patch_results.py
"""

import json
import re
from pathlib import Path


def patch_tool_call(tc: dict) -> bool:
    """Patch a single tool call's result. Returns True if changed."""
    tool = tc.get("tool", "")
    result = tc.get("result", "")
    success = tc.get("success", True)

    if not success or not result:
        return False

    changed = False

    if tool == "create" and success:
        name = tc.get("arguments", {}).get("name", "")
        prefix = f"You create {name}. "
        if result.startswith(prefix):
            # Original format: "You create a spark. tiny light"
            desc = result[len(prefix):]
            tc["result"] = f"{name} is here. {desc}"
            changed = True
        elif name and not result.startswith(f"{name} is here"):
            # Already partially patched (description only)
            tc["result"] = f"{name} is here. {result}"
            changed = True

    elif tool == "venture" and result.startswith("You have ventured to "):
        tc["result"] = "You are now at " + result[len("You have ventured to "):]
        changed = True

    elif tool == "take" and result.startswith("You take "):
        # "You take a stone. It is with you now." → "a stone is with you now."
        match = re.match(r"You take (.+?)\. It is with you now\.", result)
        if match:
            tc["result"] = f"{match.group(1)} is with you now."
            changed = True

    elif tool == "alter" and success:
        what = tc.get("arguments", {}).get("what", "")
        name = tc.get("arguments", {}).get("name", "")
        if name:
            # Rename present — strip redundant "is different now" prefix
            thing_prefix = f"{what} is different now. "
            space_prefix = "This space is now different. "
            if result.startswith(thing_prefix):
                tc["result"] = result[len(thing_prefix):]
                changed = True
            elif result.startswith(space_prefix):
                tc["result"] = result[len(space_prefix):]
                changed = True

    elif tool == "drop" and result.startswith("You release "):
        # Can't patch — we'd need the agent's location at the time
        # Leave as-is; drop hasn't been used in any sessions yet
        pass

    return changed


def patch_session(path: Path) -> int:
    """Patch a session JSON, returning count of changed tool calls."""
    data = json.loads(path.read_text(encoding="utf-8"))
    changes = 0

    for turn in data.get("turns", []):
        for tc in turn.get("tool_calls", []):
            if patch_tool_call(tc):
                changes += 1

    if changes:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return changes


if __name__ == "__main__":
    log_root = Path("logs")
    total_changes = 0

    for agent_dir in sorted(log_root.iterdir()):
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        print(f"\n{agent_dir.name}:")
        for session_file in sorted(json_dir.glob("session_*.json")):
            changes = patch_session(session_file)
            if changes:
                print(f"  {session_file.name}: {changes} results updated")
                total_changes += changes
            else:
                print(f"  {session_file.name}: no changes")

    print(f"\nDone. {total_changes} total results updated.")
    print("Re-run: palimpsest render && python scripts/preview_memory.py")
