"""
Debug script: assemble narrator and experimenter inputs for inspection.

Builds the exact user messages each agent would receive, using the
real gathering functions, and writes them to vault notes.

Usage:
    cd D:\Code\palimpsest
    python scripts/preview_inputs.py --session 1
"""

from __future__ import annotations

import argparse
import json
import yaml
from datetime import datetime, timezone
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_ROOT / "logs"
CONFIG_PATH = PROJECT_ROOT / "config"
VAULT_PATH = Path("D:/Vault/Projects/Active/Palimpsest")

# Output paths
NARRATOR_OUTPUT = VAULT_PATH / "Debug - Narrator Input.md"
EXPERIMENTER_OUTPUT = VAULT_PATH / "Debug - Experimenter Input.md"


def load_config() -> dict:
    config = {}
    for name in ["prompts", "schedule", "costs"]:
        config_file = CONFIG_PATH / f"{name}.yaml"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config[name] = yaml.safe_load(f) or {}
        else:
            config[name] = {}
    config["prompts"] = config.get("prompts", {})
    config["session"] = config.get("schedule", {}).get("session", {})
    return config


def build_narrator_preview(sessions: tuple[int, ...] | None) -> str:
    """Assemble what the narrator would see."""
    from orchestrator.narrator.narrator import (
        load_narrator_prompt,
        get_previous_entries,
        get_next_chapter_number,
        build_narrator_input,
    )
    from orchestrator.renderer import render_session_markdown

    narrator_prompt_path = VAULT_PATH / "Narrator Prompt.md"
    narrator_output_path = LOG_PATH / "narrator"

    # System prompt
    system_prompt = load_narrator_prompt(narrator_prompt_path)

    # Readable logs — bypass date filter, use session filter only
    readable_logs = []
    for agent_dir in LOG_PATH.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name == "narrator":
            continue
        readable_dir = agent_dir / "readable"
        for log_file in sorted(agent_dir.glob("session_*.json")):
            data = json.loads(log_file.read_text(encoding="utf-8"))
            if sessions and data.get("session_number") not in sessions:
                continue
            readable_file = readable_dir / log_file.name.replace(".json", ".md")
            if readable_file.exists():
                readable_logs.append(readable_file.read_text(encoding="utf-8"))
            else:
                readable_logs.append(render_session_markdown(log_file))

    # Previous entries
    previous_entries = get_previous_entries(narrator_output_path)

    # Chapter number
    chapter_number = get_next_chapter_number(narrator_output_path)

    # Build user message
    user_message = build_narrator_input(
        readable_logs=readable_logs,
        previous_entries=previous_entries,
        chapter_number=chapter_number,
    )

    # Assemble the full preview
    lines = [
        "---",
        "tags: [debug]",
        f"generated: {datetime.now().isoformat()[:19]}",
        "---",
        "",
        "# Narrator Input Preview",
        "",
        "## System Prompt",
        "",
        system_prompt,
        "",
        "---",
        "",
        "## User Message",
        "",
        user_message,
    ]
    return "\n".join(lines)


def build_experimenter_preview(sessions: tuple[int, ...] | None) -> str:
    """Assemble what the experimenter would see."""
    from orchestrator.experimenter.experimenter import (
        load_experimenter_prompt,
        gather_readable_logs_range,
        gather_narrator_chapters,
        gather_cost_summary,
        get_previous_posts,
        get_next_post_number,
        load_design_docs,
        build_experimenter_input,
        DEFAULT_DESIGN_DOC_NAMES,
    )

    config = load_config()
    experimenter_prompt_path = VAULT_PATH / "Experimenter Blog Prompt.md"
    experimenter_output_path = LOG_PATH / "experimenter"
    narrator_output_path = LOG_PATH / "narrator"

    # System prompt
    system_prompt = load_experimenter_prompt(experimenter_prompt_path)

    # Session logs
    readable_logs = gather_readable_logs_range(
        LOG_PATH, sessions=sessions,
    )

    # Narrator chapters
    chapters = gather_narrator_chapters(narrator_output_path)

    # Previous posts
    previous_posts = get_previous_posts(experimenter_output_path)

    # Design docs
    design_doc_paths = [
        VAULT_PATH / f"{name}.md"
        for name in DEFAULT_DESIGN_DOC_NAMES
    ]
    design_docs = load_design_docs(design_doc_paths)

    # Cost summary
    cost_summary = gather_cost_summary(LOG_PATH, config)

    # Post number
    post_number = get_next_post_number(experimenter_output_path)

    # Build user message
    user_message = build_experimenter_input(
        readable_logs=readable_logs,
        narrator_chapters=chapters,
        previous_posts=previous_posts,
        design_docs=design_docs,
        cost_summary=cost_summary,
        post_number=post_number,
    )

    # Assemble the full preview
    lines = [
        "---",
        "tags: [debug]",
        f"generated: {datetime.now().isoformat()[:19]}",
        "---",
        "",
        "# Experimenter Input Preview",
        "",
        "## System Prompt",
        "",
        system_prompt,
        "",
        "---",
        "",
        "## User Message",
        "",
        user_message,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Preview narrator and experimenter inputs"
    )
    parser.add_argument(
        "--session", "-s", type=int, action="append",
        help="Session number(s) to include. Can be repeated.",
    )
    args = parser.parse_args()

    sessions = tuple(args.session) if args.session else None

    print("Building narrator input preview...")
    narrator_text = build_narrator_preview(sessions)
    NARRATOR_OUTPUT.write_text(narrator_text, encoding="utf-8")
    print(f"  Saved: {NARRATOR_OUTPUT}")
    print(f"  Length: {len(narrator_text):,} chars")

    print("\nBuilding experimenter input preview...")
    experimenter_text = build_experimenter_preview(sessions)
    EXPERIMENTER_OUTPUT.write_text(experimenter_text, encoding="utf-8")
    print(f"  Saved: {EXPERIMENTER_OUTPUT}")
    print(f"  Length: {len(experimenter_text):,} chars")

    print("\nDone. Open in Obsidian to inspect.")


if __name__ == "__main__":
    main()
