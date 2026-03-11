"""
One-off migration script: restore creation times after Place unification.

The git subtree merge and file copies reset all creation times to today.
This script copies the original creation times from place_b/ and place_c/
to the corresponding files in the unified place/ directory.

Usage: python scripts/fix_creation_times.py
"""

import sys
import ctypes
from ctypes import wintypes
from pathlib import Path

EPOCH_DIFF_100NS = 116444736000000000


def get_creation_time_ns(path: Path) -> int:
    """Get a file's creation time in nanoseconds."""
    return path.stat().st_ctime_ns


def set_creation_time(path: Path, creation_time_ns: int) -> None:
    """Set a file's creation time on Windows."""
    filetime_int = (creation_time_ns // 100) + EPOCH_DIFF_100NS
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(
        str(path),
        256,   # FILE_WRITE_ATTRIBUTES
        7,     # FILE_SHARE_READ | WRITE | DELETE
        None,
        3,     # OPEN_EXISTING
        128,   # FILE_ATTRIBUTE_NORMAL
        None,
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


# Mapping: (unified place file, source file)
PROJECT = Path(__file__).resolve().parent.parent

MAPPINGS = [
    # From place_b
    ("place/here_b.md",                  "place_b/here.md"),
    ("place/the cave.md",                "place_b/the cave.md"),
    ("place/the descent.md",             "place_b/the descent.md"),
    ("place/the ember.md",               "place_b/the ember.md"),
    ("place/the garden in the dark.md",  "place_b/the garden in the dark.md"),
    ("place/the green deep.md",          "place_b/the green deep.md"),
    ("place/the marks.md",               "place_b/the marks.md"),
    ("place/the pale thing in the pool.md", "place_b/the pale thing in the pool.md"),
    ("place/Inventory.md",               "place_b/Inventory.md"),
    # From place_c
    ("place/here_c.md",                  "place_c/here.md"),
    ("place/a small stone.md",           "place_c/a small stone.md"),
    ("place/a second stone_c.md",        "place_c/a second stone.md"),
]


def main():
    if sys.platform != "win32":
        print("This script only works on Windows (creation time setting).")
        return

    for target_rel, source_rel in MAPPINGS:
        target = PROJECT / target_rel
        source = PROJECT / source_rel

        if not source.exists():
            print(f"  SKIP: source not found: {source_rel}")
            continue
        if not target.exists():
            print(f"  SKIP: target not found: {target_rel}")
            continue

        original_ctime = get_creation_time_ns(source)
        current_ctime = get_creation_time_ns(target)

        set_creation_time(target, original_ctime)

        from datetime import datetime
        orig_dt = datetime.fromtimestamp(original_ctime / 1e9)
        curr_dt = datetime.fromtimestamp(current_ctime / 1e9)
        print(f"  {target_rel}: {curr_dt:%Y-%m-%d %H:%M} → {orig_dt:%Y-%m-%d %H:%M}")

    print("\nDone.")


if __name__ == "__main__":
    main()
