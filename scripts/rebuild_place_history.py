"""
Rebuild the place git history with per-action commits and proper renames.

Replays every mutating action from every session JSON through the
PlaceInterface, committing after each one. Renames use git mv so
version history follows files across name changes.

The current place files are the authoritative final state. This script
rebuilds git's understanding of how they got there.

Safety:
- Backs up .git to .git.bak before starting
- Saves and restores all file creation times (for Obsidian graph)
- If anything goes wrong, restore with:
    rmdir /s /q place\\.git
    ren place\\.git.bak .git

Usage:
    cd D:\\Code\\palimpsest
    python scripts/rebuild_place_history.py
"""

import json
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path


def _rm_readonly(func, path, excinfo):
    """Error handler for shutil.rmtree on Windows read-only files."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.place.interface import (
    PlaceInterface, _get_creation_time_ns, _set_creation_time
)
from orchestrator.place.tools import ToolName

PLACE_PATH = Path("place")
LOG_PATH = Path("logs")

# Starting spaces — created just before each agent's first session
STARTING_SPACES = {
    "claude": "here",
    "gemini": "there",
    "deepseek": "somewhere",
}


def load_all_actions():
    """Load every mutating action from every session, sorted chronologically."""
    actions = []

    for agent_dir in sorted(LOG_PATH.iterdir()):
        if not agent_dir.is_dir():
            continue
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue

        agent_name = agent_dir.name

        for log_file in sorted(json_dir.glob("session_*.json")):
            data = json.loads(log_file.read_text(encoding="utf-8"))
            session_num = data["session_number"]
            location_start = data.get("location_start", "here")

            # Track location through the session
            current_location = location_start

            for turn in data.get("turns", []):
                for tc in turn.get("tool_calls", []):
                    tool = tc.get("tool", "")
                    args = tc.get("arguments", {})
                    result = tc.get("result", "")
                    error = tc.get("error")
                    timestamp = tc.get("timestamp", "")

                    # Track location changes
                    if tool == "go" and "You are now at" in result:
                        current_location = args.get("where", current_location)
                    elif tool == "venture" and "ventured to" in result:
                        current_location = args.get("name", current_location)

                    # Only keep mutating actions that succeeded
                    if tool in ("create", "alter", "venture", "take", "drop") and not error:
                        # Skip failed alters (e.g. "already exists")
                        if tool == "alter" and "already exists" in result:
                            continue
                        if tool == "create" and "already exists" in result:
                            continue

                        actions.append({
                            "agent": agent_name,
                            "session": session_num,
                            "tool": tool,
                            "args": args,
                            "result": result,
                            "location": current_location,
                            "timestamp": timestamp,
                        })

    # Sort by timestamp
    actions.sort(key=lambda a: a["timestamp"])
    return actions


def save_creation_times(place_path):
    """Save creation times of all files."""
    times = {}
    for f in place_path.glob("*.md"):
        ctime = _get_creation_time_ns(f)
        if ctime:
            times[f.name] = ctime
    return times


def restore_creation_times(place_path, times):
    """Restore saved creation times."""
    for filename, ctime in times.items():
        path = place_path / filename
        if path.exists():
            _set_creation_time(path, ctime)


def clear_place(place_path):
    """Remove all .md files from the place (except dotfiles/dirs)."""
    for f in place_path.glob("*.md"):
        f.unlink()


def init_git(place_path):
    """Initialise a fresh git repo."""
    import git
    repo = git.Repo.init(place_path)
    # Initial commit with .gitkeep
    gitkeep = place_path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    repo.git.add(".gitkeep")
    repo.index.commit("init")
    return repo


def create_starting_space(place_path, name):
    """Create a bare starting space note."""
    from orchestrator.place.notes import build_space_note
    path = place_path / f"{name}.md"
    fm = {
        "type": "space",
        "created_by": "place",
        "created_session": 0,
        "updated_by": "place",
        "updated_session": 0,
    }
    path.write_text(build_space_note("", [], [], fm), encoding="utf-8")


def replay_action(place, action, repo):
    """Replay a single action through the PlaceInterface and commit."""
    tool = action["tool"]
    args = action["args"]
    agent = action["agent"]
    session = action["session"]

    # Set the PlaceInterface state
    place._agent_name = agent
    place._session_number = session
    place.current_location = action["location"]

    if tool == "create":
        place.create(args["name"], args.get("description", ""))
        msg = f"{agent} s{session}: create {args['name']}"

    elif tool == "alter":
        what = args.get("what", "")
        new_name = args.get("name")
        description = args.get("description")

        if new_name and new_name != what:
            # This is a rename — use git mv for history tracking
            old_path = place.place_path / f"{what}.md"
            new_path = place.place_path / f"{new_name}.md"

            if old_path.exists() and not new_path.exists():
                # Use git mv for the rename
                repo.git.mv(str(old_path), str(new_path))

                # Now apply description/frontmatter changes on the renamed file
                from orchestrator.place.notes import parse_note, build_thing_note, build_space_note
                note = parse_note(new_path.read_text(encoding="utf-8"))
                if note:
                    fm = dict(note.frontmatter)
                    fm["updated_by"] = agent
                    fm["updated_session"] = session
                    new_desc = description if description else note.description
                    if note.note_type == "thing":
                        new_path.write_text(build_thing_note(new_desc, fm), encoding="utf-8")
                    elif note.note_type == "space":
                        new_path.write_text(build_space_note(
                            new_desc, note.spaces, note.things, fm
                        ), encoding="utf-8")

                # Update wiki links in all other files
                place._rename_all_links(what, new_name)

                msg = f"{agent} s{session}: alter {what} → {new_name}"
            else:
                # Fallback — just alter normally
                place.alter(what, description, new_name)
                msg = f"{agent} s{session}: alter {what}"
        else:
            # Description-only change
            place.alter(what, description, new_name)
            if new_name:
                msg = f"{agent} s{session}: alter {what} → {new_name}"
            else:
                msg = f"{agent} s{session}: alter {what}"

    elif tool == "venture":
        place.venture(args["name"], args.get("description", ""))
        msg = f"{agent} s{session}: venture {args['name']}"

    elif tool == "take":
        place.take(args["what"])
        msg = f"{agent} s{session}: take {args['what']}"

    elif tool == "drop":
        place.drop(args["what"])
        msg = f"{agent} s{session}: drop {args['what']}"

    else:
        return  # Unknown tool, skip

    # Commit
    repo.git.add(A=True)
    if repo.is_dirty() or repo.untracked_files:
        repo.index.commit(msg)
        print(f"  ✓ {msg}")
    else:
        print(f"  - {msg} (no changes)")


def main():
    place_path = PLACE_PATH.resolve()

    print("=== Rebuild Place Git History ===\n")

    # 1. Load all actions
    print("Loading session data...")
    actions = load_all_actions()
    print(f"  Found {len(actions)} mutating actions\n")

    # 2. Save creation times
    print("Saving file creation times...")
    creation_times = save_creation_times(place_path)
    print(f"  Saved {len(creation_times)} timestamps\n")

    # 3. Check for existing repo
    git_dir = place_path / ".git"
    if git_dir.exists():
        git_backup = place_path / ".git.bak"
        if git_backup.exists():
            print("ERROR: .git.bak already exists. Remove it first.")
            sys.exit(1)
        print("Backing up existing .git to .git.bak...")
        shutil.copytree(git_dir, git_backup)
        shutil.rmtree(git_dir, onexc=_rm_readonly)
    else:
        print("No existing git repo in place — starting fresh.")

    try:
        # 4. Clear place files (will be recreated by replay)
        print("Clearing place directory...")
        clear_place(place_path)

        # 5. Re-init
        print("Initialising fresh git repo...")
        repo = init_git(place_path)

        # 6. Replay all actions, creating starting spaces on demand
        print("Replaying actions...")
        place = PlaceInterface(place_path)
        agents_initialised = set()
        for action in actions:
            agent = action["agent"]
            if agent not in agents_initialised and agent in STARTING_SPACES:
                space_name = STARTING_SPACES[agent]
                if not (place_path / f"{space_name}.md").exists():
                    create_starting_space(place_path, space_name)
                    repo.git.add(A=True)
                    repo.index.commit(f"create starting space: {space_name}")
                    print(f"  ✓ create starting space: {space_name}")
                agents_initialised.add(agent)
            replay_action(place, action, repo)

        # 8. Restore occupants — each agent's last known location
        print("\nRestoring occupants...")
        for agent_dir in sorted(LOG_PATH.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_name = agent_dir.name
            json_dir = agent_dir / "json"
            if not json_dir.exists():
                continue
            logs = sorted(json_dir.glob("session_*.json"))
            if not logs:
                continue
            last_log = json.loads(logs[-1].read_text(encoding="utf-8"))
            last_location = last_log.get("location_end")
            if last_location:
                note_path = place_path / f"{last_location}.md"
                if note_path.exists():
                    text = note_path.read_text(encoding="utf-8")
                    if f"occupant: {agent_name}" not in text:
                        text = text.replace("---\n", f"---\noccupant: {agent_name}\n", 1)
                        # Insert after the last frontmatter field, before closing ---
                        from orchestrator.place.notes import parse_note, build_space_note
                        note = parse_note(text)
                        if note and note.note_type == "space":
                            fm = dict(note.frontmatter)
                            fm["occupant"] = agent_name
                            note_path.write_text(build_space_note(
                                note.description, note.spaces, note.things, fm
                            ), encoding="utf-8")
                            print(f"  ✓ {agent_name} occupant set at {last_location}")
        repo.git.add(A=True)
        if repo.is_dirty():
            repo.index.commit("restore occupants")

        # 9. Restore creation times
        print(f"\nRestoring file creation times...")
        restore_creation_times(place_path, creation_times)
        print(f"  Restored {len(creation_times)} timestamps")

        # 9. Verify final state
        print("\nVerifying final state...")
        current_files = sorted(f.name for f in place_path.glob("*.md"))
        expected_files = sorted(creation_times.keys())
        if current_files == expected_files:
            print("  ✓ File list matches")
        else:
            missing = set(expected_files) - set(current_files)
            extra = set(current_files) - set(expected_files)
            if missing:
                print(f"  ✗ Missing files: {missing}")
            if extra:
                print(f"  ✗ Extra files: {extra}")

        # 10. Show result
        print(f"\n=== Done ===")
        print(f"Git log now has {len(list(repo.iter_commits()))} commits")
        print(f"To verify: cd place && git log --oneline")
        print(f"To undo:   remove place\\.git and rename place\\.git.bak to place\\.git")

        # Clean up backup on success
        print(f"\n.git.bak preserved. Remove it manually once you're satisfied.")

    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nTo restore, delete place/.git and copy your backup back.")
        raise


if __name__ == "__main__":
    main()
