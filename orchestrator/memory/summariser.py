"""
Memory system for Palimpsest.

Two separate systems:

1. Agent memory — the agent's own reflections, fed back at session start.
   Recent reflections are given in full. Older ones are compressed in batches
   by Opus, preserving the agent's voice but losing detail. The compression
   is an interpretation — what gets kept and what fades is itself data.
   This is the Piranesi effect: the agent's memory of its past is reshaped
   by summarisation, and the gap is invisible from inside.

2. Ground truth summariser — factual session summaries for the narrator
   and experimental analysis. The agent never sees these. Kept separate
   so we can study the gap between what happened and what the agent remembers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RECENT_WINDOW = 10  # Number of recent reflections kept in full
BATCH_SIZE = 5  # Number of reflections per compression batch

# Models — Opus for production, Sonnet for testing
COMPRESSOR_MODEL = "claude-sonnet-4-5-20250929"  # TODO: switch to opus for production
GROUND_TRUTH_MODEL = "claude-sonnet-4-5-20250929"  # TODO: switch to opus for production

# ---------------------------------------------------------------------------
# Agent memory — what the agent receives
# ---------------------------------------------------------------------------

COMPRESSOR_PROMPT = """\
These are reflections from earlier days. They were written by you, about \
your experiences in a place you inhabit.

Compress them into a shorter account. Write in first person.

Reflections to compress:

{reflections}"""


async def compress_reflection_batch(
    reflections: list[str],
    model: str = COMPRESSOR_MODEL,
) -> str:
    """
    Compress a batch of reflections into a shorter memory.

    Uses the agent's own voice — the compression should read like
    the agent remembering, not a third party summarising.
    """
    client = anthropic.AsyncAnthropic()

    joined = "\n\n---\n\n".join(reflections)
    prompt = COMPRESSOR_PROMPT.format(reflections=joined)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


async def run_memory_compression(
    agent_name: str,
    log_path: Path,
) -> bool:
    """
    Check if compression is needed and run it.

    Compression triggers when the number of uncompressed reflections
    exceeds RECENT_WINDOW. Reflections are compressed in batches of
    BATCH_SIZE and appended to the compressed memory file.

    Returns True if compression was performed.
    """
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return False

    # Load all session logs
    logs = []
    for log_file in sorted(agent_log_dir.glob("session_*.json")):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            logs.append(data)
        except Exception as e:
            logger.warning(f"Failed to load {log_file}: {e}")

    if not logs:
        return False

    # Collect all reflections with session numbers
    all_reflections = []
    for log in logs:
        reflection = log.get("reflection", "")
        if reflection:
            all_reflections.append({
                "session": log["session_number"],
                "reflection": reflection,
            })

    # Check how many are already compressed
    compressed_file = agent_log_dir / "compressed_memory.md"
    last_compressed_session = 0
    existing_compressed = ""

    if compressed_file.exists():
        existing_compressed = compressed_file.read_text(encoding="utf-8")
        # Parse the last compressed session number from the file
        for line in existing_compressed.split("\n"):
            if line.startswith("<!-- compressed_through:"):
                try:
                    last_compressed_session = int(
                        line.split(":")[1].strip().rstrip("-->").strip()
                    )
                except (ValueError, IndexError):
                    pass

    # Split into compressed and uncompressed
    uncompressed = [
        r for r in all_reflections
        if r["session"] > last_compressed_session
    ]

    # Only compress if we have more than RECENT_WINDOW uncompressed
    if len(uncompressed) <= RECENT_WINDOW:
        return False

    # Figure out how many to compress — keep RECENT_WINDOW uncompressed
    to_compress_count = len(uncompressed) - RECENT_WINDOW

    # Round down to nearest BATCH_SIZE
    batches_to_compress = to_compress_count // BATCH_SIZE
    if batches_to_compress == 0:
        return False

    items_to_compress = batches_to_compress * BATCH_SIZE
    to_compress = uncompressed[:items_to_compress]

    # Compress in batches
    new_sections = []
    for i in range(0, len(to_compress), BATCH_SIZE):
        batch = to_compress[i:i + BATCH_SIZE]
        first_session = batch[0]["session"]
        last_session = batch[-1]["session"]
        reflections = [r["reflection"] for r in batch]

        logger.info(
            f"Compressing reflections for sessions {first_session}-{last_session}"
        )
        compressed = await compress_reflection_batch(reflections)
        new_sections.append(
            f"### Days {first_session}\u2013{last_session}\n\n{compressed}"
        )

    # Append to compressed memory file
    new_last_compressed = to_compress[-1]["session"]
    new_content = existing_compressed.rstrip()
    if new_content:
        new_content += "\n\n"
    new_content += "\n\n".join(new_sections)
    new_content += f"\n\n<!-- compressed_through: {new_last_compressed} -->\n"

    compressed_file.write_text(new_content, encoding="utf-8")
    logger.info(
        f"Compressed memory updated through session {new_last_compressed}"
    )

    return True


def build_agent_memory(
    agent_name: str,
    log_path: Path,
) -> str:
    """
    Build the memory context an agent receives at session start.

    Returns formatted memory block with compressed batches (if any)
    and recent full reflections, each labelled by day.
    """
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return ""

    # Load compressed memory if it exists
    compressed_file = agent_log_dir / "compressed_memory.md"
    last_compressed_session = 0
    compressed_text = ""

    if compressed_file.exists():
        compressed_text = compressed_file.read_text(encoding="utf-8")
        # Strip the metadata comment for agent-facing output
        lines = compressed_text.split("\n")
        clean_lines = [
            l for l in lines
            if not l.startswith("<!-- compressed_through:")
        ]
        compressed_text = "\n".join(clean_lines).strip()

        # Parse last compressed session
        for line in lines:
            if line.startswith("<!-- compressed_through:"):
                try:
                    last_compressed_session = int(
                        line.split(":")[1].strip().rstrip("-->").strip()
                    )
                except (ValueError, IndexError):
                    pass

    # Load recent reflections (after compression cutoff)
    logs = []
    for log_file in sorted(agent_log_dir.glob("session_*.json")):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            if data["session_number"] > last_compressed_session:
                logs.append(data)
        except Exception as e:
            logger.warning(f"Failed to load {log_file}: {e}")

    # Build memory block
    memory_parts = ["## Memory"]

    if compressed_text:
        memory_parts.append(compressed_text)

    for log in logs:
        reflection = log.get("reflection", "")
        if reflection:
            session_num = log["session_number"]
            memory_parts.append(f"### Day {session_num}\n\n{reflection}")

    # Return empty string if no memories
    if len(memory_parts) <= 1:
        return ""

    return "\n\n".join(memory_parts)


# ---------------------------------------------------------------------------
# Ground truth summariser — for narrator and analysis
# ---------------------------------------------------------------------------

GROUND_TRUTH_PROMPT = """\
Summarise this session concisely. Focus on:
- What the agent did (actions, creations, explorations)
- What it found or discovered
- Any notable writing or reflections
- Where it ended up

Previous sessions summary:
{previous_summary}

This session:
Agent: {agent_name}
Session: {session_number}
Started at: {location_start}
Ended at: {location_end}
Actions taken: {action_count}

Agent's own reflection:
{reflection}

Actions and events:
{session_description}

Write a 2-4 paragraph factual summary."""


async def summarise_session_ground_truth(
    session_log: dict,
    previous_summary: str | None = None,
    model: str = GROUND_TRUTH_MODEL,
) -> str:
    """
    Generate a ground-truth summary of a session.

    This is NOT given to the agent — it's for experimental analysis
    and the narrator. Factual, comprehensive, third-person.
    """
    client = anthropic.AsyncAnthropic()

    # Build a description of what happened
    actions = []
    for turn in session_log.get("turns", []):
        if turn.get("agent_text"):
            actions.append(f"Said: {turn['agent_text'][:200]}")
        for tc in turn.get("tool_calls", []):
            actions.append(
                f"Action: {tc['tool']}({json.dumps(tc['arguments'])}) "
                f"\u2192 {(tc.get('result') or '')[:100]}"
            )

    prompt = GROUND_TRUTH_PROMPT.format(
        previous_summary=previous_summary or "(First session)",
        agent_name=session_log["agent_name"],
        session_number=session_log["session_number"],
        location_start=session_log["location_start"],
        location_end=session_log.get("location_end", "unknown"),
        action_count=session_log.get("action_count", 0),
        reflection=session_log.get("reflection", "(None)"),
        session_description="\n".join(actions),
    )

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
