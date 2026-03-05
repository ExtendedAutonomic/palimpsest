"""
Narrator agent for Palimpsest.

The narrator is not an agent in the place. It cannot act, create, or move.
It reads the day's session logs — including thinking — and writes a
chapter of the ongoing chronicle.

The narrator runs after the last agent session of the day.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

NARRATOR_MODEL = "claude-opus-4-6"
MAX_OUTPUT_TOKENS = 4096

from ..pricing import calculate_cost


def load_narrator_prompt(prompt_path: Path | None = None) -> str:
    """
    Load the narrator system prompt.

    Reads from a dedicated markdown file if provided,
    otherwise falls back to prompts.yaml narrator_system.
    """
    if prompt_path and prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        # Strip YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content.strip()

    # Fallback to prompts.yaml
    raise FileNotFoundError(
        f"Narrator prompt not found at {prompt_path}. "
        "Provide a path to the narrator prompt markdown file."
    )


def gather_session_logs(
    log_path: Path,
    day: datetime | None = None,
    sessions: tuple[int, ...] | None = None,
) -> list[dict]:
    """
    Gather all session logs for a given day.

    If no day is specified, gathers logs from today.
    Returns logs sorted by session number.
    """
    if day is None:
        day = datetime.now(timezone.utc)

    target_date = day.strftime("%Y-%m-%d")
    logs = []

    for agent_dir in log_path.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name == "narrator":
            continue

        for log_file in sorted(agent_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                log_date = data.get("start_time", "")[:10]
                if log_date == target_date:
                    if sessions and data.get("session_number") not in sessions:
                        continue
                    logs.append(data)
            except Exception as e:
                logger.warning(f"Failed to load {log_file}: {e}")

    return sorted(logs, key=lambda x: x.get("session_number", 0))


def gather_readable_logs(
    log_path: Path,
    day: datetime | None = None,
    sessions: tuple[int, ...] | None = None,
) -> list[str]:
    """
    Gather readable markdown logs for a given day.

    Prefers readable/ versions if they exist, falls back to
    rendering from JSON.
    """
    if day is None:
        day = datetime.now(timezone.utc)

    target_date = day.strftime("%Y-%m-%d")
    readable_logs = []

    for agent_dir in log_path.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name == "narrator":
            continue

        readable_dir = agent_dir / "readable"
        for log_file in sorted(agent_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                if sessions:
                    # Explicit session numbers — skip date filter
                    if data.get("session_number") not in sessions:
                        continue
                else:
                    # No session filter — use date
                    log_date = data.get("start_time", "")[:10]
                    if log_date != target_date:
                        continue

                # Try readable version first
                readable_file = readable_dir / log_file.name.replace(
                    ".json", ".md"
                )
                if readable_file.exists():
                    readable_logs.append(
                        readable_file.read_text(encoding="utf-8")
                    )
                else:
                    # Fall back to rendering
                    from ..renderer import render_session_markdown
                    readable_logs.append(
                        render_session_markdown(log_file)
                    )
            except Exception as e:
                logger.warning(f"Failed to load readable log for {log_file}: {e}")

    return readable_logs


def get_previous_entries(narrator_output_path: Path) -> list[dict]:
    """
    Load previous narrator entries for continuity.

    Returns entries sorted by chapter number, each as a dict
    with 'chapter', 'title', and 'content' keys.
    """
    entries = []

    if not narrator_output_path.exists():
        return entries

    for entry_file in sorted(narrator_output_path.glob("chapter_*.md")):
        try:
            content = entry_file.read_text(encoding="utf-8")
            # Parse chapter number from filename
            chapter_num = int(entry_file.stem.split("_")[1])
            # Parse title from first heading
            title = ""
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            entries.append({
                "chapter": chapter_num,
                "title": title,
                "content": content,
            })
        except Exception as e:
            logger.warning(f"Failed to load narrator entry {entry_file}: {e}")

    return sorted(entries, key=lambda x: x["chapter"])


def get_next_chapter_number(narrator_output_path: Path) -> int:
    """Get the next chapter number based on existing entries."""
    if not narrator_output_path.exists():
        return 1
    existing = list(narrator_output_path.glob("chapter_*.md"))
    if not existing:
        return 1
    numbers = []
    for f in existing:
        try:
            numbers.append(int(f.stem.split("_")[1]))
        except (ValueError, IndexError):
            pass
    return max(numbers) + 1 if numbers else 1


def build_narrator_input(
    readable_logs: list[str],
    previous_entries: list[dict],
    chapter_number: int,
) -> str:
    """
    Build the user message for the narrator.

    Assembles: previous entries (for continuity), the day's
    session logs, and the chapter number to write.
    """
    parts = []

    # Previous entries for continuity
    if previous_entries:
        parts.append("## Your previous entries\n")
        for entry in previous_entries:
            parts.append(f"### Chapter {entry['chapter']}: {entry['title']}\n")
            # Include full content for recent entries, summary for older ones
            parts.append(entry["content"])
            parts.append("")

    # Session logs
    parts.append("## Today's session logs\n")
    for log_md in readable_logs:
        parts.append(log_md)
        parts.append("\n---\n")

    # Instruction
    parts.append(f"Write Chapter {chapter_number}.")

    return "\n".join(parts)


async def run_narrator(
    log_path: Path,
    narrator_prompt_path: Path,
    narrator_output_path: Path | None = None,
    day: datetime | None = None,
    model: str = NARRATOR_MODEL,
    sessions: tuple[int, ...] | None = None,
) -> Path:
    """
    Run the narrator for a given day.

    Gathers session logs, sends them with the narrator system prompt,
    and saves the resulting chapter.

    Returns the path to the saved chapter file.
    """
    if narrator_output_path is None:
        narrator_output_path = log_path / "narrator"
    narrator_output_path.mkdir(parents=True, exist_ok=True)

    if day is None:
        day = datetime.now(timezone.utc)

    # Load the narrator system prompt
    system_prompt = load_narrator_prompt(narrator_prompt_path)
    logger.info(f"Narrator system prompt loaded ({len(system_prompt):,} chars) from {narrator_prompt_path}")

    # Gather the day's readable logs
    readable_logs = gather_readable_logs(log_path, day, sessions)
    if not readable_logs:
        raise ValueError(
            f"No session logs found for {day.strftime('%Y-%m-%d')}. "
            "Nothing to narrate."
        )

    # Track which sessions were included
    session_logs_raw = gather_session_logs(log_path, day, sessions)
    included_sessions = sorted(s["session_number"] for s in session_logs_raw if "session_number" in s)

    # Get previous entries
    previous_entries = get_previous_entries(narrator_output_path)

    # Determine chapter number
    chapter_number = get_next_chapter_number(narrator_output_path)

    # Build the input
    user_message = build_narrator_input(
        readable_logs=readable_logs,
        previous_entries=previous_entries,
        chapter_number=chapter_number,
    )

    logger.info(
        f"Running narrator for {day.strftime('%Y-%m-%d')} "
        f"(Chapter {chapter_number}, {len(readable_logs)} session logs)"
    )

    # Call the API
    client = anthropic.AsyncAnthropic()

    response = await client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    narrator_text = response.content[0].text

    # Token usage and cost
    usage = response.usage
    narrator_cost = calculate_cost(model, usage.input_tokens, usage.output_tokens)
    total_narrator_tokens = usage.input_tokens + usage.output_tokens

    logger.info(
        f"Narrator tokens — input: {usage.input_tokens:,}, "
        f"output: {usage.output_tokens:,}, cost: ${narrator_cost:.2f}"
    )

    # Append session stats footer
    sessions_str = ""
    if included_sessions:
        sessions_str = " · Sessions: " + ", ".join(str(s) for s in included_sessions)
    footer = (
        f"\n\n---\n"
        f"Session stats: {model} · {total_narrator_tokens:,} tokens · ${narrator_cost:.2f}{sessions_str}"
    )

    # Save the chapter
    output_file = narrator_output_path / f"chapter_{chapter_number:04d}.md"
    output_file.write_text(narrator_text + footer, encoding="utf-8")

    # Save cost sidecar — same structure as session logs for palimpsest costs
    sidecar = {
        "model": model,
        "tokens": {"input": usage.input_tokens, "output": usage.output_tokens},
        "cost": narrator_cost,
    }
    sidecar_file = narrator_output_path / f"chapter_{chapter_number:04d}.json"
    sidecar_file.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    logger.info(f"Chapter {chapter_number} saved to {output_file}")

    return output_file
