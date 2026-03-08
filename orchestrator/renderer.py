"""
Session log renderer — converts JSON session logs to readable markdown.

Supports two output formats:
- "obsidian": Obsidian-native with callouts, wiki links, collapsible sections
- "github": GitHub-flavoured markdown with HTML details, GitHub alerts, plain text refs
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import re


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _place_ref(name: str, fmt: str) -> str:
    """Format a reference to a place or thing in the world."""
    if fmt == "github":
        return name
    return f"[[{name}]]"


def _session_ref(
    agent: str, session_num: int, display: str | None = None, fmt: str = "obsidian"
) -> str:
    """Format a reference to another session log."""
    label = display or f"Session {session_num}"
    if fmt == "github":
        return f"[{label}](session_{session_num:04d}.md)"
    return f"[[logs/{agent}/obsidian_logs/session_{session_num:04d}|{label}]]"


def _render_thinking(thinking: str, fmt: str) -> list[str]:
    """Render an agent thinking block."""
    lines = []
    if fmt == "github":
        lines.append("<details open>")
        lines.append("<summary>\U0001f4ad Thinking</summary>")
        lines.append("")
        for line in thinking.strip().split("\n"):
            if line.strip():
                lines.append(f"> *{line}*")
            else:
                lines.append(">")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    else:
        lines.append("> [!tip]+ Thinking")
        for line in thinking.strip().split("\n"):
            lines.append(f"> {line}")
        lines.append("")
    return lines


def _render_callout(
    callout_type: str, title: str, content: str, fmt: str
) -> list[str]:
    """Render a callout block (dusk, reflect, etc.)."""
    lines = []
    if fmt == "github":
        lines.append("> [!NOTE]")
        for line in content.strip().split("\n"):
            lines.append(f"> `{line}`")
        lines.append("")
    else:
        lines.append(f"> [!{callout_type}] {title}")
        for line in content.strip().split("\n"):
            lines.append(f"> {line}")
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Memory rendering
# ---------------------------------------------------------------------------

def _compressed_memory_ref(agent: str, label: str, fmt: str) -> str:
    """Format a reference to the compressed memory file."""
    if fmt == "github":
        return f"[{label}](../compressed_memory.md)"
    return f"[[logs/{agent}/compressed_memory|{label}]]"


def _render_opening_with_memory(opening: str, agent: str, fmt: str) -> list[str]:
    """
    Replace the full memory dump with compact references.

    Obsidian: wiki-linked references to compressed memory + raw session logs.
    GitHub: relative markdown links.
    """
    lines = []

    # Extract the location line from the end
    location_match = re.search(r"You are at: (.+)", opening)
    location = location_match.group(1).strip() if location_match else None

    # Find compressed references — both old format ("Days 1-3") and
    # new week format ("Week 1 (Days 1-7)" or "Week 2 (Days 8)")
    # Range weeks: Week N (Days X–Y)
    week_ranges = re.findall(
        r"Week\s+\d+\s+\(Days\s+(\d+)[\u2013\-](\d+)\)", opening
    )
    # Single-day weeks: Week N (Days X) — no range
    week_singles = re.findall(
        r"Week\s+\d+\s+\(Days?\s+(\d+)\)", opening
    )
    # Old format: "### Days 1-3"
    batch_matches = re.findall(
        r"(?:#{1,3}\s+)?Days\s+(\d+)[\u2013\-](\d+)", opening
    )
    # Build a unified set of compressed session numbers
    compressed_sessions = set()
    for start, end in week_ranges + batch_matches:
        for s in range(int(start), int(end) + 1):
            compressed_sessions.add(s)
    for s in week_singles:
        compressed_sessions.add(int(s))
    compressed = bool(compressed_sessions)

    # Find individual day references: "Day 1" or "### Day 1"
    individual = [int(m) for m in re.findall(r"(?:^|\n)(?:#{1,3}\s+)?Day\s+(\d+)", opening)]

    # Remove any individual days that fall within compressed ranges
    individual = [d for d in individual if d not in compressed_sessions]

    # Build the memory reference line
    parts = []
    if compressed:
        label = f"Days {min(compressed_sessions)}\u2013{max(compressed_sessions)} (compressed)"
        parts.append(_compressed_memory_ref(agent, label, fmt))
    for day_num in sorted(set(individual)):
        parts.append(_session_ref(agent, day_num, f"Day {day_num}", fmt))

    if parts:
        lines.append(f"> Memory: {', '.join(parts)}")
    if location:
        lines.append(f"> `You are at: {location}`" if fmt == "github" else f"> You are at: {location}")

    return lines


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_session_markdown(
    log_path: Path, place_path: Path | None = None, fmt: str = "obsidian"
) -> str:
    """Render a session JSON log as readable markdown.

    Args:
        log_path: Path to the session JSON log file.
        place_path: Optional path to the place directory (unused, reserved).
        fmt: Output format — "obsidian" or "github".
    """
    data = json.loads(log_path.read_text(encoding="utf-8"))

    agent = data["agent_name"]
    session = data["session_number"]
    phase = data.get("phase", 1)
    start = datetime.fromisoformat(data["start_time"])
    end = datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None
    actions = data.get("action_count", 0)
    tokens = data.get("tokens", {})
    total_tokens = (
        tokens.get("input", 0)
        + tokens.get("cache_creation", 0)
        + tokens.get("cache_read", 0)
        + tokens.get("output", 0)
    )
    location_start = data.get("location_start", "?")
    location_end = data.get("location_end", "?")
    model = data.get("model", "")

    lines = []

    # Frontmatter
    lines.append("---")
    lines.append("type: session")
    lines.append(f"agent: {agent}")
    lines.append(f"session: {session}")
    lines.append(f"phase: {phase}")
    lines.append(f"date: {start.strftime('%Y-%m-%d')}")
    if model:
        lines.append(f"model: {model}")
    lines.append(f"actions: {actions}")
    lines.append(f"tokens: {total_tokens:,}")
    cost = data.get("cost")
    if cost is not None:
        lines.append(f"cost: ${cost:.2f}")
    if end:
        duration_secs = int((end - start).total_seconds())
        lines.append(f"duration: {duration_secs // 60}m {duration_secs % 60}s")
    lines.append(f"location: {location_start} \u2192 {location_end}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {agent.title()} \u2014 Session {session}")
    lines.append("")
    phase_names = {
        1: "The Solitary",
        2: "The Other",
        3: "Contact",
        4: "The Third",
        5: "The Reveal",
    }
    phase_name = phase_names.get(phase, f"Phase {phase}")
    lines.append(f"*Phase {phase}: {phase_name}*")
    if end:
        lines.append("")
        lines.append(
            f"*{start.strftime('%d %B %Y, %H:%M')}\u2013{end.strftime('%H:%M')} UTC*"
        )
    lines.append("")
    if fmt == "obsidian":
        lines.append("---")
        lines.append("")

    # System prompt
    system_prompt = data.get("system_prompt")
    if system_prompt:
        lines.append("## System")
        lines.append("")
        for line in system_prompt.strip().split("\n"):
            lines.append(f"> {line}")
        lines.append("")

    # Opening prompt
    opening = data.get("opening_prompt")
    if opening:
        lines.append("## Opening")
        lines.append("")
        if opening.strip().startswith("## Memory"):
            # Session 2+: replace full memory with compact references
            if fmt == "github":
                lines.append("> [!NOTE]")
            lines.extend(_render_opening_with_memory(opening, agent, fmt))
        else:
            # Session 1: just show the founding prompt
            if fmt == "github":
                lines.append("> [!NOTE]")
            for line in opening.strip().split("\n"):
                lines.append(f"> `{line}`" if fmt == "github" else f"> {line}")
        lines.append("")

    # Dusk prompt (if it was sent)
    dusk = data.get("dusk_prompt")
    dusk_turn_threshold = data.get("dusk_action", 14)

    if fmt == "obsidian":
        lines.append("---")

    # Turns
    lines.append("## Day")
    lines.append("")

    dusk_shown = False

    for turn_idx, turn in enumerate(data.get("turns", [])):
        # Show dusk prompt before the turn that responded to it
        if dusk and not dusk_shown and turn_idx >= dusk_turn_threshold:
            if fmt == "obsidian":
                lines.append("---")
            lines.append("## Dusk")
            lines.append("")
            lines.extend(_render_callout("dusk", "Dusk", dusk, fmt))

            dusk_shown = True

        # Thinking (inline)
        thinking = turn.get("thinking")
        if thinking:
            lines.extend(_render_thinking(thinking, fmt))

        # Agent text
        text = turn.get("agent_text", "").strip()
        if text:
            lines.append(text)
            lines.append("")

        # Show nudge if one was sent after this turn
        nudge = turn.get("nudge")
        if nudge:
            if fmt == "github":
                lines.append(f"> `{nudge}`")
            else:
                lines.append(f"> *{nudge}*")
            lines.append("")

        # Tool calls
        for tc in turn.get("tool_calls", []):
            tool = tc.get("tool", "?")
            args = tc.get("arguments", {})
            result = tc.get("result", "")

            # Format the tool call — wiki links in Obsidian, plain text in GitHub
            # GitHub uses backtick code for tool names to distinguish actions visually
            if fmt == "github":
                tool_fmt = f"`{tool}:`"
            else:
                tool_fmt = f"**{tool}**"
            q = '"' if fmt == "obsidian" else ""
            if tool == "perceive":
                lines.append(f"> {tool_fmt}")
            elif tool == "go":
                where = args.get("where", "?")
                ref = "back" if where == "back" else _place_ref(where, fmt)
                arg_fmt = f"`{ref}`" if fmt == "github" else f"{q}{ref}{q}"
                lines.append(f"> {tool_fmt} {arg_fmt}")
            elif tool in ("venture", "examine", "create", "build"):
                arg_key = "name" if tool in ("venture", "create", "build") else "what"
                arg_val = args.get(arg_key, "?")
                ref = _place_ref(arg_val, fmt)
                arg_fmt = f"`{ref}`" if fmt == "github" else f"{q}{ref}{q}"
                lines.append(f"> {tool_fmt} {arg_fmt}")
            elif tool == "alter":
                what = args.get("what", "?")
                ref = _place_ref(what, fmt)
                arg_fmt = f"`{ref}`" if fmt == "github" else f"{q}{ref}{q}"
                lines.append(f"> {tool_fmt} {arg_fmt}")
                new_name = args.get("name", "")
                if new_name:
                    new_ref = _place_ref(new_name, fmt)
                    lines.append(f"> *renamed to {q}{new_ref}{q}*")
            else:
                lines.append(f"> {tool_fmt}")

            # Format the result — for alter, append the description
            display_result = result
            if tool == "alter":
                desc = args.get("description", "")
                if desc:
                    display_result = f"{result} {desc}"
            if display_result:
                if fmt == "github":
                    # Two trailing spaces on previous line forces <br> without blank line
                    lines[-1] = lines[-1] + "  "
                result_lines = display_result.strip().split("\n")
                for rl in result_lines:
                    if rl.strip():
                        lines.append(f"> *{rl}*")
                    else:
                        lines.append(">")

            lines.append("")

    # Reflect prompt and reflection
    reflect_prompt = data.get("reflect_prompt")
    reflection = data.get("reflection", "")
    if reflect_prompt or reflection:
        if fmt == "obsidian":
            lines.append("---")
        lines.append("## Reflection")
        lines.append("")
    if reflect_prompt:
        lines.extend(_render_callout("reflect", "Reflect", reflect_prompt, fmt))
    if reflection:
        lines.append(reflection.strip())
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def save_readable_log(log_path: Path, output_dir: Path | None = None) -> Path:
    """Render a session log and save it as Obsidian-formatted markdown."""
    if output_dir is None:
        output_dir = log_path.parent.parent / "obsidian_logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    md = render_session_markdown(log_path, fmt="obsidian")
    output_file = output_dir / log_path.name.replace(".json", ".md")
    output_file.write_text(md, encoding="utf-8")
    return output_file


def save_github_log(log_path: Path, output_dir: Path | None = None) -> Path:
    """Render a session log and save it as GitHub-formatted markdown."""
    if output_dir is None:
        output_dir = log_path.parent.parent / "github_logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    md = render_session_markdown(log_path, fmt="github")
    output_file = output_dir / log_path.name.replace(".json", ".md")
    output_file.write_text(md, encoding="utf-8")
    return output_file
