"""
Memory system for Palimpsest.

Agent memory — the agent's full session logs, fed back at session start.
Recent sessions are rendered in full as readable markdown. Older ones are
compressed in batches, preserving the agent's voice but losing detail.
The compression is an interpretation — what gets kept and what fades is
itself data. This is the Piranesi effect: the agent's memory of its past
is reshaped by summarisation, and the gap is invisible from inside.
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

RECENT_WINDOW = 3  # Number of recent sessions kept in full
BATCH_SIZE = 3  # Number of sessions per compression batch

# Models — Opus for production, Sonnet for testing
COMPRESSOR_MODEL = "claude-sonnet-4-5-20250929"  # Intentionally Sonnet — compression is mechanical, not interpretive

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

    # Track turn index to insert dusk at the right point
    dusk_prompt = (session_data.get("dusk_prompt") or "").strip()
    dusk_turn = session_data.get("dusk_action")  # Now stores turn index
    dusk_inserted = False

    for turn_idx, turn in enumerate(session_data.get("turns", [])):
        # Insert dusk prompt before the turn that responded to it
        if dusk_prompt and not dusk_inserted and dusk_turn is not None and turn_idx >= dusk_turn:
            parts.append(dusk_prompt)
            dusk_inserted = True

        # Thinking
        thinking = turn.get("thinking", "").strip() if turn.get("thinking") else ""
        if thinking:
            parts.append(f"*Thinking: {thinking}*")

        # Agent's words
        agent_text = turn.get("agent_text", "").strip()
        if agent_text:
            parts.append(agent_text)

        # Nudge (injected user message after no-tool-call turns)
        nudge = turn.get("nudge")
        if nudge:
            parts.append(nudge)

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
) -> tuple[str, dict]:
    """
    Compress a batch of rendered session logs into a shorter memory.

    Uses the agent's own voice — the compression should read like
    the agent remembering, not a third party summarising.

    Returns (compressed_text, token_counts).
    """
    client = anthropic.AsyncAnthropic()

    joined = "\n\n---\n\n".join(rendered_sessions)
    prompt = COMPRESSOR_PROMPT.format(sessions=joined)

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    token_counts = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    return response.content[0].text, token_counts


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
    total_input_tokens = 0
    total_output_tokens = 0
    for i in range(0, len(to_compress), BATCH_SIZE):
        batch = to_compress[i:i + BATCH_SIZE]
        first_session = batch[0]["session_number"]
        last_session = batch[-1]["session_number"]
        rendered = [render_session_log(log) for log in batch]

        logger.info(
            f"Compressing sessions {first_session}-{last_session}"
        )
        compressed, token_counts = await compress_session_batch(rendered)
        total_input_tokens += token_counts["input"]
        total_output_tokens += token_counts["output"]
        new_sections.append(
            f"Days {first_session}\u2013{last_session}\n\n{compressed}"
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

    # Persist compression token costs
    _record_compression_cost(
        agent_log_dir, COMPRESSOR_MODEL, total_input_tokens, total_output_tokens
    )

    return True


def _record_compression_cost(
    agent_log_dir: Path,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Append compression token usage to the agent's compression_costs.json."""
    costs_file = agent_log_dir / "compression_costs.json"
    existing: list[dict] = []
    if costs_file.exists():
        try:
            existing = json.loads(costs_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    from datetime import datetime, timezone
    existing.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })
    costs_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


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
            memory_parts.append(f"Day {session_num}\n\n{rendered}")

    # Return empty string if no memories
    if len(memory_parts) <= 1:
        return ""

    return "\n\n---\n\n".join(memory_parts)

