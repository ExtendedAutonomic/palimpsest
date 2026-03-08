"""
Fix creation times for all place files based on session JSON timestamps.

Reads every session JSON, finds the tool call that first brought each
entity into existence, and sets its filesystem creation time to match.
Tracks rename chains so that renamed files keep their original creation time.

Usage:
    cd D:\\Code\\palimpsest
    python scripts/fix_creation_times.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.place.interface import _set_creation_time

LOG_PATH = Path("logs")
PLACE_PATH = Path("place")

# Starting spaces — timestamps just before each agent's first session
STARTING_SPACES = {
    "here.md": "2026-03-03T20:23:30+00:00",
    "there.md": "2026-03-07T15:01:00+00:00",
}


def iso_to_ctime_ns(iso_str):
    """Convert ISO timestamp to nanoseconds for _set_creation_time."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def find_creation_times():
    """Find the original creation timestamp for each place file.

    Tracks rename chains: if B was renamed from A, B gets A's creation time.
    """
    # Maps current filename → creation timestamp (nanoseconds)
    creation_times = {}
    # Maps old_name → new_name for rename tracking
    rename_chain = {}

    # Starting spaces
    for filename, ts in STARTING_SPACES.items():
        creation_times[filename] = iso_to_ctime_ns(ts)

    # Scan all sessions chronologically
    all_sessions = []
    for agent_dir in sorted(LOG_PATH.iterdir()):
        if not agent_dir.is_dir():
            continue
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        for log_file in sorted(json_dir.glob("session_*.json")):
            data = json.loads(log_file.read_text(encoding="utf-8"))
            all_sessions.append(data)

    all_sessions.sort(key=lambda s: s.get("start_time", ""))

    for session in all_sessions:
        for turn in session.get("turns", []):
            for tc in turn.get("tool_calls", []):
                tool = tc.get("tool", "")
                args = tc.get("arguments", {})
                result = tc.get("result", "")
                error = tc.get("error")
                timestamp = tc.get("timestamp", "")

                if error or not timestamp:
                    continue

                # New entity created
                if tool == "create" and "already exists" not in result:
                    filename = f"{args.get('name', '')}.md"
                    if filename not in creation_times:
                        creation_times[filename] = iso_to_ctime_ns(timestamp)

                elif tool == "venture" and "ventured to" in result:
                    filename = f"{args.get('name', '')}.md"
                    if filename not in creation_times:
                        creation_times[filename] = iso_to_ctime_ns(timestamp)

                # Rename — new file inherits old file's creation time
                elif tool == "alter" and "already exists" not in result:
                    new_name = args.get("name")
                    old_name = args.get("what")
                    if new_name and old_name and f"now called {new_name}" in result:
                        old_filename = f"{old_name}.md"
                        new_filename = f"{new_name}.md"
                        # Inherit creation time from the original
                        if old_filename in creation_times:
                            creation_times[new_filename] = creation_times[old_filename]
                        else:
                            # Shouldn't happen, but fall back to rename timestamp
                            creation_times[new_filename] = iso_to_ctime_ns(timestamp)

    return creation_times


def main():
    place_path = PLACE_PATH.resolve()
    creation_times = find_creation_times()

    existing_files = {f.name for f in place_path.glob("*.md")}

    print("Fixing creation times...\n")

    fixed = 0
    for filename, ctime_ns in sorted(creation_times.items()):
        if filename not in existing_files:
            continue

        filepath = place_path / filename
        _set_creation_time(filepath, ctime_ns)

        dt = datetime.fromtimestamp(ctime_ns / 1_000_000_000, tz=timezone.utc)
        print(f"  ✓ {filename} → {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        fixed += 1

    orphans = existing_files - set(creation_times.keys())
    if orphans:
        print(f"\n  WARNING: No creation time found for: {orphans}")

    print(f"\nFixed {fixed} files.")


if __name__ == "__main__":
    main()
