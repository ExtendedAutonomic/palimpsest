"""
Memory system for Palimpsest.

Two separate systems:

1. Agent memory — the agent's full session logs, fed back at session start.
Recent sessions are rendered in full as readable markdown. Older ones are
compressed in batches by Opus, preserving the agent's voice but losing
detail. The compression is an interpretation — what gets kept and what
fades is itself data. This is the Piranesi effect: the agent's memory of
its past is reshaped by summarisation, and the gap is invisible from inside.

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

RECENT_WINDOW = 10  # Number of recent sessions kept in full
BATCH_SIZE = 5  # Number of sessions per compression batch

# Models — Opus for production, Sonnet for testing
COMPRESSOR_MODEL = "claude-sonnet-4-5-20250929"  # TODO: switch to opus for production
GROUND_TRUTH_MODEL = "claude-sonnet-4-5-20250929"  # TODO: switch to opus for production

# ---------------------------------------------------------------------------
# Agent memory — what the agent receives
# ---------------------------------------------------------------------------


# Arguments to omit from rendered tool calls (too long, echoed in results)
_OMIT_ARGS = {"description"}


def render_session_log(session_data: dict) -> str:
    """
    Render a session JSON into readable markdown for the agent's memory.

    Shows the agent's thinking, words, actions, and results — the complete
    experience of a session as the agent lived it. Dusk prompt included
    at the correct point. Reflect prompt and reflection included at the end.
    """
    parts = []

    # Track action count to insert dusk at the right point
    dusk_prompt = (session_data.get("dusk_prompt") or "").strip()
    dusk_action = session_data.get("dusk_action")
    dusk_inserted = False
    action_count = 0

    for turn in session_data.get("turns", []):
        # Thinking
        thinking = turn.get("thinking", "").strip() if turn.get("thinking") else ""
        if thinking:
            parts.append(f"*Thinking: {thinking}*")

        # Agent's words
        agent_text = turn.get("agent_text", "").strip()
        if agent_text:
            parts.append(agent_text)

        # Tool calls and results
        for tc in turn.get("tool_calls", []):
            tool_name = tc.get("tool", "")
            args = tc.get("arguments", {})

            # Format the action (omit description args — echoed in results)
            display_args = {k: v for k, v in args.items() if k not in _OMIT_ARGS}
            if display_args:
                arg_parts = [f"{k}: {v}" for k, v in display_args.items()]
                parts.append(f"[{tool_name}: {', '.join(arg_parts)}]")
            else:
                parts.append(f"[{tool_name}]")

            # Result
            result = tc.get("result", "")
            error = tc.get("error", "")
            if error:
                parts.append(error)
            elif result:
                parts.append(result)

            action_count += 1

            # Insert dusk prompt after the action that triggered it
            if dusk_prompt and not dusk_inserted and dusk_action is not None and action_count >= dusk_action:
                parts.append(dusk_prompt)
                dusk_inserted = True

    # Reflect prompt and reflection at the end
    reflect_prompt = (session_data.get("reflect_prompt") or "").strip()
    if reflect_prompt:
        parts.append(reflect_prompt)

    reflection = (session_data.get("reflection") or "").strip()
    if reflection:
        parts.append(reflection)

    return "\n\n".join(parts)


COMPRESSOR_PROMPT = """\
These are records of your earlier days in a place you inhabit — what you \
did, what you found, and what you thought.

Compress them into a shorter account. Write in first person. Preserve \
what matters most — what you created, what you discovered, what surprised you.

Session logs to compress:

{sessions}"""


async def compress_session_batch(
    rendered_sessions: list[str],
    model: str = COMPRESSOR_MODEL,
) -> str:
    """
    Compress a batch of rendered session logs into a shorter memory.

    Uses the agent's own voice — the compression should read like
    the agent remembering, not a third party summarising.
    """
    client = anthropic.AsyncAnthropic()

    joined = "\n\n---\n\n".join(rendered_sessions)
    prompt = COMPRESSOR_PROMPT.format(sessions=joined)

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


async def run_memory_compression(
    agent_name: str,
    log_path: Path,
) -> bool:
    """
    Check if compression is needed and run it.

    Compression triggers when the number of uncompressed sessions
    exceeds RECENT_WINDOW. Sessions are rendered to markdown, compressed
    in batches of BATCH_SIZE, and appended to the compressed memory file.

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
        log for log in logs
        if log["session_number"] > last_compressed_session
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
        first_session = batch[0]["session_number"]
        last_session = batch[-1]["session_number"]
        rendered = [render_session_log(log) for log in batch]

        logger.info(
            f"Compressing sessions {first_session}-{last_session}"
        )
        compressed = await compress_session_batch(rendered)
        new_sections.append(
            f"### Days {first_session}\u2013{last_session}\n\n{compressed}"
        )

    # Append to compressed memory file
    new_last_compressed = to_compress[-1]["session_number"]
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
    and recent full session logs rendered as readable markdown,
    each labelled by day.
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

    # Load recent session logs (after compression cutoff)
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
        session_num = log["session_number"]
        rendered = render_session_log(log)
        if rendered.strip():
            memory_parts.append(f"### Day {session_num}\n\n{rendered}")

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
