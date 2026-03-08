"""
One-off migration: add success field to existing session JSON tool calls.

Uses the Place's known failure message prefixes to determine success/failure
retroactively. After this, all session logs have the success field and the
renderer can use it directly.

Run from the palimpsest root:
    python scripts/patch_success.py
"""

import json
from pathlib import Path

# Known failure prefixes from the Place interface
FAILURE_PREFIXES = [
    "There is nothing",
    "There is no space",
    "Something called",
    "You cannot",
    "You are not in",
    "You must",
    "You do not",
    "You already have",
    "This is not a space",
    "Something prevented",
    "That name is not possible",
]

# Results starting with a quote are errors like '"a stone" is not a space.'
def _starts_with_quote(s: str) -> bool:
    return s.startswith('"')


def is_failure(result: str, error: str | None) -> bool:
    if error:
        return True
    if not result:
        return False
    if _starts_with_quote(result):
        return True
    return any(result.startswith(prefix) for prefix in FAILURE_PREFIXES)


def patch_session(path: Path) -> tuple[int, int]:
    """Patch a session JSON, returning (total_tool_calls, failures_found)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    total = 0
    failures = 0

    for turn in data.get("turns", []):
        for tc in turn.get("tool_calls", []):
            total += 1
            result = tc.get("result", "")
            error = tc.get("error")
            success = not is_failure(result, error)
            tc["success"] = success
            if not success:
                failures += 1

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return total, failures


if __name__ == "__main__":
    log_root = Path("logs")
    for agent_dir in sorted(log_root.iterdir()):
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        print(f"\n{agent_dir.name}:")
        for session_file in sorted(json_dir.glob("session_*.json")):
            total, failures = patch_session(session_file)
            status = f"({failures} failures)" if failures else "(all success)"
            print(f"  {session_file.name}: {total} tool calls {status}")

    print("\nDone. Re-run preview_memory.py to verify.")
