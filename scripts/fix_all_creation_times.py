"""
Fix all creation times in the unified Place directory.

Scans session logs for the exact tool call timestamp when each entity
was created, and sets the file's creation time to match. For founding
spaces (created_session: 0), uses session 1's start_time minus 5 seconds.

Usage: python scripts/fix_all_creation_times.py
"""

import sys
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime, timedelta, timezone

EPOCH_DIFF_100NS = 116444736000000000
PROJECT = Path(__file__).resolve().parent.parent
PLACE = PROJECT / "place"
LOGS = PROJECT / "logs"


def set_creation_time(path: Path, creation_time_ns: int) -> None:
    filetime_int = (creation_time_ns // 100) + EPOCH_DIFF_100NS
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(
        str(path), 256, 7, None, 3, 128, None,
    )
    if handle == -1:
        print(f"  ERROR: could not open {path}")
        return
    try:
        ft = wintypes.FILETIME(
            filetime_int & 0xFFFFFFFF,
            (filetime_int >> 32) & 0xFFFFFFFF,
        )
        kernel32.SetFileTime(handle, ctypes.byref(ft), None, None)
    finally:
        kernel32.CloseHandle(handle)


def dt_to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1e9)


def load_session(agent: str, session: int) -> dict | None:
    log_file = LOGS / agent / "json" / f"session_{session:04d}.json"
    if not log_file.exists():
        return None
    return json.loads(log_file.read_text(encoding="utf-8"))


def build_creation_index() -> dict[tuple[str, str], datetime]:
    """Scan all session logs and find the exact create timestamp for each entity.
    
    Returns a dict mapping (agent, entity_name) -> datetime of the create tool call.
    For entities that were renamed via alter, tracks the original name's
    create time under the new name.
    """
    index: dict[tuple[str, str], datetime] = {}
    renames: dict[str, str] = {}  # old_name -> new_name

    # Scan all agents
    if not LOGS.exists():
        return index

    for agent_dir in sorted(LOGS.iterdir()):
        if not agent_dir.is_dir():
            continue
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue

        agent_name = agent_dir.name

        for log_file in sorted(json_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            for turn in data.get("turns", []):
                for tc in turn.get("tool_calls", []):
                    tool = tc.get("tool", "")
                    args = tc.get("arguments", {})
                    success = tc.get("success", True)
                    ts_str = tc.get("timestamp")

                    if not success or not ts_str:
                        continue

                    ts = datetime.fromisoformat(ts_str)

                    if tool in ("create", "venture"):
                        name = args.get("name", "")
                        key = (agent_name, name)
                        if name and key not in index:
                            index[key] = ts

                    elif tool == "alter":
                        old_name = args.get("what", "")
                        new_name = args.get("name", "")
                        if new_name and old_name:
                            old_key = (agent_name, old_name)
                            new_key = (agent_name, new_name)
                            renames[old_name] = new_name
                            # The new name inherits the original create time
                            if old_key in index and new_key not in index:
                                index[new_key] = index[old_key]

    return index


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def main():
    if sys.platform != "win32":
        print("This script only works on Windows.")
        return

    print("Scanning session logs for create timestamps...\n")
    creation_index = build_creation_index()

    print(f"Found {len(creation_index)} entities in logs.\n")
    print("Scanning Place files...\n")

    changes = []
    skips = []

    for path in sorted(PLACE.glob("*.md")):
        filename = path.stem
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)

        # The display name is what the entity is called in the Place
        display_name = fm.get("name", filename)
        agent = fm.get("created_by")
        session = fm.get("created_session")

        if session == 0:
            # Founding space — use session 1 start minus 5 seconds
            lookup_agent = fm.get("updated_by", agent)
            if lookup_agent == "place":
                lookup_agent = agent
            session_data = load_session(lookup_agent, 1)
            if session_data:
                s1_time = datetime.fromisoformat(session_data["start_time"])
                correct_time = s1_time - timedelta(seconds=5)
            else:
                skips.append((filename, f"no session 1 found for {lookup_agent}"))
                continue
        elif (agent, display_name) in creation_index:
            correct_time = creation_index[(agent, display_name)]
        elif (agent, filename) in creation_index:
            correct_time = creation_index[(agent, filename)]
        else:
            skips.append((filename, "not found in any session log"))
            continue

        current_ns = path.stat().st_ctime_ns
        correct_ns = dt_to_ns(correct_time)
        current_dt = datetime.fromtimestamp(current_ns / 1e9)

        # Only fix if off by more than 2 seconds
        if abs(current_ns - correct_ns) > 2_000_000_000:
            changes.append((path, filename, display_name, current_dt, correct_time, correct_ns))

    if changes:
        print(f"Fixing {len(changes)} files:\n")
        for path, filename, display_name, current_dt, correct_time, correct_ns in changes:
            label = filename if filename == display_name else f"{filename} ({display_name})"
            print(f"  {label}")
            print(f"    {current_dt:%Y-%m-%d %H:%M:%S} → {correct_time:%Y-%m-%d %H:%M:%S}")
            set_creation_time(path, correct_ns)
    else:
        print("All creation times are correct.\n")

    if skips:
        print(f"\nSkipped {len(skips)} files:")
        for name, reason in skips:
            print(f"  {name}: {reason}")

    print("\nDone.")


if __name__ == "__main__":
    main()
