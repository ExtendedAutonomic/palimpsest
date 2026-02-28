"""
Session log renderer — converts JSON session logs to readable markdown.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def render_session_markdown(log_path: Path, place_path: Path | None = None) -> str:
    """Render a session JSON log as readable markdown."""
    data = json.loads(log_path.read_text(encoding="utf-8"))

    agent = data["agent_name"]
    session = data["session_number"]
    phase = data["phase"]
    start = datetime.fromisoformat(data["start_time"])
    end = datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None
    actions = data.get("action_count", 0)
    tokens = data.get("tokens", {})
    total_tokens = tokens.get("input", 0) + tokens.get("output", 0)
    location_start = data.get("location_start", "?")
    location_end = data.get("location_end", "?")

    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f"agent: {agent}")
    lines.append(f"session: {session}")
    lines.append(f"phase: {phase}")
    lines.append(f"date: {start.strftime('%Y-%m-%d')}")
    lines.append(f"actions: {actions}")
    lines.append(f"tokens: {total_tokens:,}")
    lines.append(f"location: {location_start} → {location_end}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {agent.title()} — Session {session}")
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
            f"*{start.strftime('%d %B %Y, %H:%M')}–{end.strftime('%H:%M')} UTC*"
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
        for line in opening.strip().split("\n"):
            lines.append(f"> {line}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Turns
    lines.append("## The Session")
    lines.append("")

    for turn in data.get("turns", []):
        # Thinking (inline, as callout)
        thinking = turn.get("thinking")
        if thinking:
            lines.append("> [!thought]+ Thinking")
            for think_line in thinking.strip().split("\n"):
                lines.append(f"> {think_line}")
            lines.append("")

        # Agent text
        text = turn.get("agent_text", "").strip()
        if text:
            lines.append(text)
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
            elif tool == "build":
                name = args.get("name", "?")
                lines.append(f"> **build** \"[[{name}]]\"")
            else:
                lines.append(f"> **{tool}**")

            # Format the result (first line only for brevity)
            if result:
                first_line = result.split("\n")[0]
                lines.append(f"> *{first_line}*")

            lines.append("")

    # Reflection
    reflection = data.get("reflection", "")
    if reflection:
        lines.append("---")
        lines.append("")
        lines.append("## Reflection")
        lines.append("")
        lines.append(reflection.strip())
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
