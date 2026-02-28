"""
Memory summariser for Palimpsest.

Implements the hybrid memory system: agent self-authored reflections
are preserved as-is, while a separate "ground truth" summary is maintained
for experimental analysis.

The agent receives its own memories. We keep the ground truth.
The gap between them is data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


async def summarise_session(
    session_log: dict,
    previous_summary: str | None = None,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """
    Generate a ground-truth summary of a session.

    This is NOT given to the agent — it's for experimental analysis.
    Uses a cheaper model since this is infrastructure, not the experiment.
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
                f"→ {(tc.get('result') or '')[:100]}"
            )

    session_description = "\n".join(actions)

    prompt = f"""Summarise this session concisely. Focus on:
- What the agent did (actions, creations, explorations)
- What it found or discovered
- Any notable writing or reflections
- Where it ended up

Previous sessions summary:
{previous_summary or "(First session)"}

This session:
Agent: {session_log['agent_name']}
Session: {session_log['session_number']}
Started at: {session_log['location_start']}
Ended at: {session_log.get('location_end', 'unknown')}
Actions taken: {session_log.get('action_count', 0)}

Agent's own reflection:
{session_log.get('reflection', '(None)')}

Actions and events:
{session_description}

Write a 2-4 paragraph factual summary."""

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def build_agent_memory(
    agent_name: str,
    log_path: Path,
    max_sessions: int = 10,
) -> str:
    """
    Build the memory context an agent receives at session start.

    Uses the agent's own reflections (self-authored memory) plus
    compressed summaries of older sessions.
    """
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return ""

    # Load all session logs, sorted by session number
    logs = []
    for log_file in sorted(agent_log_dir.glob("session_*.json")):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            logs.append(data)
        except Exception as e:
            logger.warning(f"Failed to load {log_file}: {e}")

    if not logs:
        return ""

    # Build memory from reflections
    # Recent sessions: full reflections
    # Older sessions: compressed
    memory_parts = []

    if len(logs) <= max_sessions:
        # All sessions fit — use full reflections
        for log in logs:
            session_num = log["session_number"]
            reflection = log.get("reflection", "")
            if reflection:
                memory_parts.append(
                    f"Day {session_num}: {reflection}"
                )
    else:
        # Compress older sessions, keep recent ones full
        # Load ground truth summaries if available
        summary_file = agent_log_dir / "cumulative_summary.txt"
        if summary_file.exists():
            memory_parts.append(
                f"Your earlier days (summarised):\n{summary_file.read_text(encoding='utf-8')}"
            )

        # Recent sessions: full reflections
        recent = logs[-max_sessions:]
        for log in recent:
            session_num = log["session_number"]
            reflection = log.get("reflection", "")
            if reflection:
                memory_parts.append(
                    f"Day {session_num}: {reflection}"
                )

    return "\n\n".join(memory_parts)
