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
    return f"[[{agent.title()} \u2014 Session {session_num}|{label}]]"


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

def _render_opening_with_memory(opening: str, agent: str, fmt: str) -> list[str]:
    """
    Replace the full memory dump with compact references.

    Obsidian: wiki-linked session references.
    GitHub: relative markdown links.
    """
    lines = []

    # Extract the location line from the end
    location_match = re.search(r"You are at: (.+)", opening)
    location = location_match.group(1).strip() if location_match else None

    # Find compressed batch references: "Days 1-3" or "Days 1–3"
    compressed = re.findall(r"Days\s+(\d+)[–\-](\d+)", opening)

    # Find individual day references: "Day 1", "Day 2" etc.
    individual = [int(m) for m in re.findall(r"(?:^|\n)Day\s+(\d+)", opening)]

    # Remove any individual days that fall within compressed ranges
    compressed_sessions = set()
    for start, end in compressed:
        for s in range(int(start), int(end) + 1):
            compressed_sessions.add(s)
    individual = [d for d in individual if d not in compressed_sessions]

    # Build the memory reference line
    parts = []
    for start, end in compressed:
        parts.append(f"Days {start}\u2013{end} (compressed)")
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
            tool_fmt = f"`{tool}`" if fmt == "github" else f"**{tool}**"
            q = "" if fmt == "github" else '"'
            if tool == "perceive":
                lines.append(f"> {tool_fmt}")
            elif tool == "go":
                where = args.get("where", "?")
                if where == "back":
                    lines.append(f"> {tool_fmt} {q}back{q}")
                else:
                    ref = _place_ref(where, fmt)
                    lines.append(f"> {tool_fmt} {q}{ref}{q}")
            elif tool == "venture":
                name = args.get("name", "?")
                ref = _place_ref(name, fmt)
                lines.append(f"> {tool_fmt} {q}{ref}{q}")
            elif tool == "examine":
                what = args.get("what", "?")
                ref = _place_ref(what, fmt)
                lines.append(f"> {tool_fmt} {q}{ref}{q}")
            elif tool == "create":
                name = args.get("name", "?")
                ref = _place_ref(name, fmt)
                lines.append(f"> {tool_fmt} {q}{ref}{q}")
            elif tool == "alter":
                what = args.get("what", "?")
                ref = _place_ref(what, fmt)
                lines.append(f"> {tool_fmt} {q}{ref}{q}")
                new_name = args.get("name", "")
                if new_name:
                    new_ref = _place_ref(new_name, fmt)
                    lines.append(f"> *renamed to {q}{new_ref}{q}*")
            elif tool == "build":
                name = args.get("name", "?")
                ref = _place_ref(name, fmt)
                lines.append(f"> {tool_fmt} {q}{ref}{q}")
            else:
                lines.append(f"> {tool_fmt}")

            # Format the result — for alter, append the description
            display_result = result
            if tool == "alter":
                desc = args.get("description", "")
                if desc:
                    display_result = f"{result} {desc}"
            if display_result:
                result_lines = display_result.strip().split("\n")
                for rl in result_lines:
                    if rl.strip():
                        if fmt == "github":
                            lines.append(f"> `{rl}`")
                        else:
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
        output_dir = log_path.parent / "readable"
    output_dir.mkdir(parents=True, exist_ok=True)

    md = render_session_markdown(log_path, fmt="obsidian")
    output_file = output_dir / log_path.name.replace(".json", ".md")
    output_file.write_text(md, encoding="utf-8")
    return output_file


def save_github_log(log_path: Path, output_dir: Path | None = None) -> Path:
    """Render a session log and save it as GitHub-formatted markdown."""
    if output_dir is None:
        output_dir = log_path.parent / "github"
    output_dir.mkdir(parents=True, exist_ok=True)

    md = render_session_markdown(log_path, fmt="github")
    output_file = output_dir / log_path.name.replace(".json", ".md")
    output_file.write_text(md, encoding="utf-8")
    return output_file
