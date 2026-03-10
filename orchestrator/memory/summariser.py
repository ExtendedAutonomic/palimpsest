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

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (defaults — can be overridden per agent via agents.yaml)
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


def natural_action(tool_name: str, args: dict, success: bool) -> str | None:
    """Return a natural-language action line for a tool call.

    Uses declarative voice on success (*You alter X.*) and attempt
    language on failure (*You try to alter X.*) so the action line
    doesn't imply success when the world rejected the action.

    The success bool comes from the Place — each tool method returns
    (success, message) and execute_tool stores it on the ToolCall.
    """
    verb_prefix = "" if success else "try to "

    if tool_name == "perceive":
        return f"*You {verb_prefix}perceive.*"
    elif tool_name == "go":
        where = args.get("where", "?")
        return f"*You {verb_prefix}go to {where}.*"
    elif tool_name == "examine":
        what = args.get("what", "?")
        return f"*You {verb_prefix}examine {what}.*"
    elif tool_name == "create":
        name = args.get("name", "?")
        return f"*You {verb_prefix}create {name}.*"
    elif tool_name == "alter":
        what = args.get("what", "?")
        new_name = args.get("name")
        if new_name:
            return f"*You {verb_prefix}alter {what} → {new_name}.*"
        return f"*You {verb_prefix}alter {what}.*"
    elif tool_name == "venture":
        name = args.get("name", "?")
        return f"*You {verb_prefix}venture toward {name}.*"
    elif tool_name == "take":
        what = args.get("what", "?")
        return f"*You {verb_prefix}take {what}.*"
    elif tool_name == "drop":
        what = args.get("what", "?")
        return f"*You {verb_prefix}drop {what}.*"
    return None


def render_session_log(session_data: dict) -> str:
    """
    Render a session JSON into readable markdown for the agent's memory.

    Shows the agent's thinking, words, actions, and results — the complete
    experience of a session as the agent lived it. Dusk prompt included
    at the correct point. Reflect prompt and reflection included at the end.

    Tool calls are rendered as natural-language action lines (*You alter X.*)
    with attempt language on failure (*You try to alter X.*). The success
    bool is read from the session JSON (set by the Place at execution time).
    Old logs without the success field default to True for compatibility.
    """
    parts = []

    # Include the founding prompt for session 1 — the first thing
    # the agent experienced. Skip for later sessions where the opening
    # prompt is the memory block (which would be recursive).
    opening = (session_data.get("opening_prompt") or "").strip()
    if opening and not opening.startswith("## Memory"):
        parts.append(f"[{opening}]")

    # Track turn index to insert dusk at the right point
    dusk_prompt = (session_data.get("dusk_prompt") or "").strip()
    dusk_turn = session_data.get("dusk_action")  # Now stores turn index
    dusk_inserted = False

    for turn_idx, turn in enumerate(session_data.get("turns", [])):
        # Insert dusk prompt before the turn that responded to it
        if dusk_prompt and not dusk_inserted and dusk_turn is not None and turn_idx >= dusk_turn:
            parts.append(f"[{dusk_prompt}]")
            dusk_inserted = True

        # Thinking
        thinking = turn.get("thinking", "").strip() if turn.get("thinking") else ""
        if thinking:
            parts.append("---")
            parts.append(f"*Thinking: {thinking}*")
            parts.append("---")

        # Agent's words — prefixed with "you:" so the agent can
        # distinguish its own output from the companion's in memory.
        # Skip the label for tool-only turns (actions speak for themselves).
        agent_text = turn.get("agent_text", "").strip()
        tool_calls = turn.get("tool_calls", [])
        if agent_text:
            parts.append(f"you: {agent_text}")
        elif not tool_calls:
            parts.append("you:")

        # Nudge (injected user message after no-tool-call turns)
        # Bracketed with [response: ...] — square brackets mark
        # non-agent content (consistent with system prompts)
        nudge = turn.get("nudge")
        if nudge:
            parts.append(f"[response: {nudge}]")

        # Tool calls and results
        for tc in turn.get("tool_calls", []):
            tool_name = tc.get("tool", "")
            args = tc.get("arguments", {})

            result = tc.get("result", "")
            error = tc.get("error", "")
            success = tc.get("success", True)  # Old logs lack this field

            # Natural-language action line — experiential context without
            # exposing function-call syntax (which Gemini mimics as text
            # output when it sees it in memory).
            action_line = natural_action(tool_name, args, success)
            if action_line:
                parts.append(action_line)

            # Result — blockquoted as the world's response, distinct
            # from the agent's own words
            if error:
                parts.append(f"> {error}")
            elif result:
                result_lines = result.strip().split("\n")
                parts.append("\n".join(f"> {line}" if line.strip() else ">" for line in result_lines))

    # Reflect prompt and reflection at the end
    reflect_prompt = (session_data.get("reflect_prompt") or "").strip()
    if reflect_prompt:
        parts.append(f"[{reflect_prompt}]")

    reflection = (session_data.get("reflection") or "").strip()
    if reflection:
        parts.append(f"you: {reflection}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Rolling compression
# ---------------------------------------------------------------------------

ROLLING_COMPRESS_PROMPT = """\
You are maintaining your memories of your days in a place you inhabit.

Here is your memory so far:

{existing_memory}

---

Here is a new day to weave into your memory:

### Day {session_number}

{new_day}

---

Update your memory to include this new day. Keep the week \
structure: use "### Week N (Days X\u2013Y)" headings. If this day starts a \
new week, begin a new section.

Write the way memory works \u2014 keeping what felt important, letting the \
rest go. First person. Match the voice and register of the originals. \
Weave in original wording where it matters.

Do not add bullet points, bold text, or numbered lists. Do not clean up \
uncertainty or make the account more coherent than the original.

Output only the memory text, starting with the first ### Week heading."""

FIRST_COMPRESS_PROMPT = """\
You are creating a memory of your first days in a place you inhabit.

{sessions}

---

Compress your existing memories into a shorter account, organised by week. Use \
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


async def run_memory_compression(
    agent_name: str,
    log_path: Path,
    *,
    compressor_model: str | None = None,
    recent_window: int | None = None,
    days_per_week: int | None = None,
    enabled: bool = True,
) -> bool:
    """
    Rolling memory compression.

    After each session, checks if there are more than recent_window
    uncompressed sessions. If so, compresses one day at a time into
    the rolling memory, until exactly recent_window remain uncompressed.

    The compressor always sees the full compressed memory plus the new
    day, preserving arcs and context across the entire history.

    Parameters can be overridden per agent via agents.yaml compression
    settings. Falls back to module-level defaults if not provided.

    Returns True if compression was performed.
    """
    if not enabled:
        return False

    # Resolve parameters — per-agent overrides or module defaults
    model = compressor_model or COMPRESSOR_MODEL
    window = recent_window if recent_window is not None else RECENT_WINDOW
    # days_per_week is used in the prompt template via week headings;
    # currently embedded in the prompt text. Reserved for future use.
    _ = days_per_week if days_per_week is not None else DAYS_PER_WEEK

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

    # Only compress if we have more than window uncompressed
    if len(uncompressed) <= window:
        return False

    # Compress one day at a time until exactly window remain
    to_compress = uncompressed[:-window]

    total_input_tokens = 0
    total_output_tokens = 0
    compressed_count = 0

    for log in to_compress:
        session_num = log["session_number"]
        rendered = render_session_log(log)

        if not compressed_body:
            # First compression — no existing memory yet
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
                    rendered_batch, model=model,
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
                    rendered_batch, model=model,
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
                model=model,
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
        model, total_input_tokens, total_output_tokens
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
        f"model: {model}\n"
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
        agent_log_dir, model, total_input_tokens, total_output_tokens
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

    result = memory_parts[0]  # "## Memory"
    if len(memory_parts) > 1:
        result += "\n\n" + "\n\n---\n\n".join(memory_parts[1:])
    return result
