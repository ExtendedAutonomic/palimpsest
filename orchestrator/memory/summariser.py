"""
Memory system for Palimpsest.

Agent memory — the agent's full session logs, fed back at session start.
The two most recent sessions are kept in full. Everything older is
compressed into a rolling summary that grows one day at a time.

The compression is rolling, not batched. After each session, the oldest
uncompressed day is woven into the existing compressed memory — the way
real memory works. Each new experience modifies your understanding of
everything that came before it. The compressor reads the full story so
far and adds one chapter. Week boundaries provide natural structure.

This is the Piranesi effect: the agent's memory of its past is reshaped
by summarisation, and the gap is invisible from inside.
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

RECENT_WINDOW = 2  # Number of recent sessions kept in full
DAYS_PER_WEEK = 7  # Sessions per "week" in compressed memory

# Opus for compression — preserves voice and register better than Sonnet,
# which tends to editorialise and impose retrospective structure.
COMPRESSOR_MODEL = "claude-opus-4-6"

# ---------------------------------------------------------------------------
# Agent memory — what the agent receives
# ---------------------------------------------------------------------------



def _parse_compressed_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a compressed memory file.

    Returns (frontmatter_dict, body_text).
    """
    if not text.startswith("---"):
        # Legacy format — check for HTML comment
        last_compressed = 0
        for line in text.split("\n"):
            if line.startswith("<!-- compressed_through:"):
                try:
                    last_compressed = int(
                        line.split(":")[1].strip().rstrip("-->").strip()
                    )
                except (ValueError, IndexError):
                    pass
        body = "\n".join(
            l for l in text.split("\n")
            if not l.startswith("<!-- compressed_through:")
        ).strip()
        return {"compressed_through": last_compressed}, body

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    import yaml
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}
    body = parts[2].strip()
    return fm, body


def _strip_compressed_frontmatter(text: str) -> str:
    """Return the body of a compressed memory file, stripping frontmatter
    and legacy HTML comments."""
    _, body = _parse_compressed_frontmatter(text)
    return body


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
        # Blockquoted so the agent can distinguish nudges from its own
        # ellipses in memory — without this, the agent's "..." and the
        # nudge "..." are indistinguishable, creating a feedback loop
        # where the agent learns to produce more silence from its own
        # memory of undifferentiated silence
        nudge = turn.get("nudge")
        if nudge:
            parts.append(f"> {nudge}")

        # Tool calls and results
        for tc in turn.get("tool_calls", []):
            tool_name = tc.get("tool", "")
            args = tc.get("arguments", {})

            # Format as function call syntax — bracket notation caused
            # Gemini to mimic it as text output instead of generating
            # actual API tool calls
            if args:
                arg_parts = [f'{k}="{v}"' for k, v in args.items()]
                parts.append(f"{tool_name}({', '.join(arg_parts)})")
            else:
                parts.append(f"{tool_name}()")

            # Result — blockquoted as the world's response, distinct
            # from the agent's own words
            result = tc.get("result", "")
            error = tc.get("error", "")
            if error:
                parts.append(f"> {error}")
            elif result:
                result_lines = result.strip().split("\n")
                parts.append("\n".join(f"> {line}" if line.strip() else ">" for line in result_lines))

    # Reflect prompt and reflection at the end
    reflect_prompt = (session_data.get("reflect_prompt") or "").strip()
    if reflect_prompt:
        parts.append(reflect_prompt)

    reflection = (session_data.get("reflection") or "").strip()
    if reflection:
        parts.append(reflection)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Rolling compression
# ---------------------------------------------------------------------------

ROLLING_COMPRESS_PROMPT = """\
You are maintaining a compressed memory of your days in a place you inhabit.

Here is your memory so far:

{existing_memory}

---

Here is a new day to weave into your memory:

### Day {session_number}

{new_day}

---

Rewrite your complete memory, now including this new day. Keep the week \
structure: use "### Week N (Days X\u2013Y)" headings. If this day starts a \
new week, begin a new section. If it belongs to the current week, expand \
that section.

Write the way memory works \u2014 keeping what felt important, letting the \
rest go. First person. Match the voice and register of the originals. \
Weave in original wording where it matters.

Do not add bullet points, bold text, or numbered lists. Do not clean up \
uncertainty or make the account more coherent than the original.

Output only the memory text, starting with the first ### Week heading."""

FIRST_COMPRESS_PROMPT = """\
You are compressing a record of your first days in a place you inhabit \
into a memory.

{sessions}

---

Compress this into a shorter account, organised by week. Use \
"### Week 1 (Days {first}\u2013{last})" as the heading.

Write the way memory works \u2014 keeping what felt important, letting the \
rest go. First person. Match the voice and register of the original. \
Weave in original wording where it matters.

Do not add bullet points, bold text, or numbered lists. Do not clean up \
uncertainty or make the account more coherent than the original.

Output only the memory text, starting with the ### Week heading."""


async def _compress_rolling(
    existing_memory: str,
    new_day_rendered: str,
    session_number: int,
    model: str = COMPRESSOR_MODEL,
) -> tuple[str, dict]:
    """Weave one new day into the existing compressed memory.

    The compressor reads the full story so far and produces an updated
    version that includes the new day. This preserves inter-session arcs
    that would be lost if days were compressed in isolation.

    Returns (updated_memory_text, token_counts).
    """
    client = anthropic.AsyncAnthropic()

    prompt = ROLLING_COMPRESS_PROMPT.format(
        existing_memory=existing_memory,
        session_number=session_number,
        new_day=new_day_rendered,
    )

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    token_counts = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    return response.content[0].text, token_counts


async def _compress_first(
    rendered_sessions: list[tuple[int, str]],
    model: str = COMPRESSOR_MODEL,
) -> tuple[str, dict]:
    """Compress the first batch of sessions when no existing memory exists.

    Used for bootstrapping — after this, rolling compression takes over.

    Returns (compressed_text, token_counts).
    """
    client = anthropic.AsyncAnthropic()

    session_parts = []
    for session_num, rendered in rendered_sessions:
        session_parts.append(f"### Day {session_num}\n\n{rendered}")
    joined = "\n\n---\n\n".join(session_parts)

    first = rendered_sessions[0][0]
    last = rendered_sessions[-1][0]

    prompt = FIRST_COMPRESS_PROMPT.format(
        sessions=joined,
        first=first,
        last=last,
    )

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    token_counts = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    return response.content[0].text, token_counts


# Keep the old function for backward compatibility
async def compress_session_batch(
    rendered_sessions: list[str],
    model: str = COMPRESSOR_MODEL,
) -> tuple[str, dict]:
    """Legacy batch compression. Use _compress_first or _compress_rolling instead."""
    return await _compress_first(
        [(i + 1, r) for i, r in enumerate(rendered_sessions)],
        model=model,
    )


async def run_memory_compression(
    agent_name: str,
    log_path: Path,
) -> bool:
    """
    Rolling memory compression.

    After each session, checks if there are more than RECENT_WINDOW
    uncompressed sessions. If so, compresses one day at a time into
    the rolling memory, until exactly RECENT_WINDOW remain uncompressed.

    The compressor always sees the full compressed memory plus the new
    day, preserving arcs and context across the entire history.

    Returns True if compression was performed.
    """
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return False

    # Load all session logs
    json_dir = agent_log_dir / "json"
    logs = []
    if json_dir.exists():
        for log_file in sorted(json_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                logs.append(data)
            except Exception as e:
                logger.warning(f"Failed to load {log_file}: {e}")

    if not logs:
        return False

    # Load existing compressed memory
    compressed_file = agent_log_dir / "compressed_memory.md"
    last_compressed_session = 0
    existing_compressed = ""
    compressed_body = ""

    if compressed_file.exists():
        existing_compressed = compressed_file.read_text(encoding="utf-8")
        fm, compressed_body = _parse_compressed_frontmatter(existing_compressed)
        last_compressed_session = fm.get("compressed_through", 0)

    # Find uncompressed sessions
    uncompressed = [
        log for log in logs
        if log["session_number"] > last_compressed_session
    ]

    # Only compress if we have more than RECENT_WINDOW uncompressed
    if len(uncompressed) <= RECENT_WINDOW:
        return False

    # Compress one day at a time until exactly RECENT_WINDOW remain
    to_compress = uncompressed[:-RECENT_WINDOW]

    total_input_tokens = 0
    total_output_tokens = 0
    compressed_count = 0

    for log in to_compress:
        session_num = log["session_number"]
        rendered = render_session_log(log)

        if not compressed_body:
            # First compression — no existing memory yet
            # If there's only one day, compress it alone
            # If multiple days accumulated, compress them together
            remaining = to_compress[compressed_count:]
            if len(remaining) > 1:
                # Bootstrap: compress all pending at once
                rendered_batch = [
                    (l["session_number"], render_session_log(l))
                    for l in remaining
                ]
                logger.info(
                    f"Bootstrapping memory: days "
                    f"{remaining[0]['session_number']}\u2013"
                    f"{remaining[-1]['session_number']}"
                )
                compressed_body, token_counts = await _compress_first(
                    rendered_batch,
                )
                total_input_tokens += token_counts["input"]
                total_output_tokens += token_counts["output"]
                last_compressed_session = remaining[-1]["session_number"]
                compressed_count = len(to_compress)
                break
            else:
                # Single first day
                logger.info(f"Bootstrapping memory: day {session_num}")
                rendered_batch = [(session_num, rendered)]
                compressed_body, token_counts = await _compress_first(
                    rendered_batch,
                )
                total_input_tokens += token_counts["input"]
                total_output_tokens += token_counts["output"]
                last_compressed_session = session_num
                compressed_count += 1
        else:
            # Rolling compression — weave this day into existing memory
            logger.info(f"Compressing day {session_num} into memory")
            compressed_body, token_counts = await _compress_rolling(
                existing_memory=compressed_body,
                new_day_rendered=rendered,
                session_number=session_num,
            )
            total_input_tokens += token_counts["input"]
            total_output_tokens += token_counts["output"]
            last_compressed_session = session_num
            compressed_count += 1

    if compressed_count == 0:
        return False

    # Calculate compression cost (cumulative across all runs)
    from ..pricing import calculate_cost
    run_cost = calculate_cost(
        COMPRESSOR_MODEL, total_input_tokens, total_output_tokens
    )
    run_tokens = total_input_tokens + total_output_tokens

    # Accumulate with any existing totals from previous compressions
    existing_fm, _ = _parse_compressed_frontmatter(existing_compressed)
    prev_tokens = existing_fm.get("tokens", 0)
    if isinstance(prev_tokens, str):
        prev_tokens = int(prev_tokens.replace(",", ""))
    prev_cost_str = str(existing_fm.get("cost", "$0.00"))
    prev_cost = float(prev_cost_str.lstrip("$"))
    total_compression_tokens = prev_tokens + run_tokens
    compression_cost = round(prev_cost + run_cost, 2)

    # Build frontmatter
    from datetime import datetime, timezone
    frontmatter = (
        f"---\n"
        f"type: compressed_memory\n"
        f"agent: {agent_name}\n"
        f"model: {COMPRESSOR_MODEL}\n"
        f"compressed_through: {last_compressed_session}\n"
        f"tokens: {total_compression_tokens:,}\n"
        f"cost: ${compression_cost:.2f}\n"
        f"updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"---\n\n"
    )

    compressed_file.write_text(frontmatter + compressed_body + "\n", encoding="utf-8")
    logger.info(
        f"Compressed memory updated through session {last_compressed_session}"
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
    json_dir = agent_log_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    costs_file = json_dir / "compression_costs.json"
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

    Returns formatted memory block with compressed memory (if any)
    and the most recent RECENT_WINDOW full session logs rendered as
    readable markdown, each labelled by day.
    """
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return ""

    # Load compressed memory if it exists
    compressed_file = agent_log_dir / "compressed_memory.md"
    last_compressed_session = 0
    compressed_text = ""

    if compressed_file.exists():
        raw = compressed_file.read_text(encoding="utf-8")
        fm, compressed_text = _parse_compressed_frontmatter(raw)
        last_compressed_session = fm.get("compressed_through", 0)

    # Load recent session logs (after compression cutoff)
    json_dir = agent_log_dir / "json"
    logs = []
    if json_dir.exists():
        for log_file in sorted(json_dir.glob("session_*.json")):
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

    return "\n\n---\n\n".join(memory_parts)
