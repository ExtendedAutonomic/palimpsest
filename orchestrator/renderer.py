"""
Session log renderer — converts JSON session logs to readable markdown.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


import re


def _render_opening_with_memory(opening: str, agent: str) -> list[str]:
    """
    Replace the full memory dump with compact wiki-linked references.

    Instead of embedding the entire memory in the rendered log,
    list which sessions were provided as memory with links.
    """
    lines = []
    agent_title = agent.title()

    # Extract the location line from the end
    location_match = re.search(r"You are at: (.+)", opening)
    location = location_match.group(1).strip() if location_match else None

    # Find compressed batch references: "Days 1–3" or "Days 1-3"
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
        parts.append(
            f"[[{agent_title} \u2014 Session {day_num}|Day {day_num}]]"
        )

    if parts:
        lines.append(f"> Memory: {', '.join(parts)}")
    if location:
        lines.append(f"> You are at: {location}")

    return lines


def render_session_markdown(log_path: Path, place_path: Path | None = None) -> str:
    """Render a session JSON log as readable markdown."""
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
        lines.append(
            f"*{start.strftime('%d %B %Y, %H:%M')}\u2013{end.strftime('%H:%M')} UTC*"
        )
    lines.append("")
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
            lines.extend(_render_opening_with_memory(opening, agent))
        else:
            # Session 1: just show the founding prompt
            for line in opening.strip().split("\n"):
                lines.append(f"> {line}")
        lines.append("")

    # Dusk prompt (if it was sent)
    dusk = data.get("dusk_prompt")
    dusk_turn_threshold = data.get("dusk_action", 14)  # Turn index when dusk was sent

    lines.append("---")

    # Turns
    lines.append("## Day")
    lines.append("")

    dusk_shown = False

    for turn_idx, turn in enumerate(data.get("turns", [])):
        # Show dusk prompt before the turn that responded to it
        if dusk and not dusk_shown and turn_idx >= dusk_turn_threshold:
            lines.append("---")
            lines.append("## Dusk")
            lines.append("")
            lines.append("> [!dusk] Dusk")
            for dusk_line in dusk.strip().split("\n"):
                lines.append(f"> {dusk_line}")
            lines.append("")
            dusk_shown = True

        # Thinking (inline, as callout)
        thinking = turn.get("thinking")
        if thinking:
            lines.append("> [!tip]+ Thinking")
            for think_line in thinking.strip().split("\n"):
                lines.append(f"> {think_line}")
            lines.append("")

        # Agent text
        text = turn.get("agent_text", "").strip()
        if text:
            lines.append(text)
            lines.append("")

        # Show nudge if one was sent after this turn
        nudge = turn.get("nudge")
        if nudge:
            lines.append(f"> *{nudge}*")
            lines.append("")

        # Tool calls
        for tc in turn.get("tool_calls", []):
            tool = tc.get("tool", "?")
            args = tc.get("arguments", {})
            result = tc.get("result", "")

            # Format the tool call with wiki links for create/build/venture
            if tool == "perceive":
                lines.append("> **perceive**")
            elif tool == "go":
                where = args.get("where", "?")
                if where == "back":
                    lines.append("> **go** \"back\"")
                else:
                    lines.append(f"> **go** \"[[{where}]]\"")
            elif tool == "venture":
                name = args.get("name", "?")
                lines.append(f"> **venture** \"[[{name}]]\"")
            elif tool == "examine":
                what = args.get("what", "?")
                lines.append(f"> **examine** \"[[{what}]]\"")
            elif tool == "create":
                name = args.get("name", "?")
                lines.append(f"> **create** \"[[{name}]]\"")
            elif tool == "alter":
                what = args.get("what", "?")
                lines.append(f"> **alter** \"[[{what}]]\"")
                new_name = args.get("name", "")
                if new_name:
                    lines.append(f"> *renamed to \"[[{new_name}]]\"*")
            elif tool == "build":
                name = args.get("name", "?")
                lines.append(f"> **build** \"[[{name}]]\"")
            else:
                lines.append(f"> **{tool}**")

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
                        lines.append(f"> *{rl}*")
                    else:
                        lines.append(">")

            lines.append("")

    # Reflect prompt and reflection
    reflect_prompt = data.get("reflect_prompt")
    reflection = data.get("reflection", "")
    if reflect_prompt or reflection:
        lines.append("---")
        lines.append("## Reflection")
        lines.append("")
    if reflect_prompt:
        lines.append("> [!reflect] Reflect")
        for reflect_line in reflect_prompt.strip().split("\n"):
            lines.append(f"> {reflect_line}")
        lines.append("")
    if reflection:
        lines.append(reflection.strip())
        lines.append("")

    # Session stats footer
    duration_str = ""
    if end:
        duration_secs = int((end - start).total_seconds())
        duration_str = f" \u00b7 {duration_secs // 60}m {duration_secs % 60}s"
    cost_str = ""
    cost = data.get("cost")
    if cost is not None:
        cost_str = f" \u00b7 ${cost:.2f}"
    lines.append("---")
    lines.append(
        f"Session stats: {model} \u00b7 {actions} actions \u00b7 {total_tokens:,} tokens{cost_str}{duration_str}"
    )
    lines.append("")

    return "\n".join(lines)


def save_readable_log(log_path: Path, output_dir: Path | None = None) -> Path:
    """Render a session log and save it as markdown."""
    if output_dir is None:
        output_dir = log_path.parent / "readable"
    output_dir.mkdir(parents=True, exist_ok=True)

    md = render_session_markdown(log_path)
    output_file = output_dir / log_path.name.replace(".json", ".md")
    output_file.write_text(md, encoding="utf-8")
    return output_file
