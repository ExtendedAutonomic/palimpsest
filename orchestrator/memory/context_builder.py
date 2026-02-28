"""
Context builder for Palimpsest.

Assembles the full context an agent receives at the start of each session:
memory + place diff + current location state.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .diff_tracker import format_diff_for_agent, get_place_diff
from .summariser import build_agent_memory

logger = logging.getLogger(__name__)


def build_session_context(
    agent_name: str,
    place_path: Path,
    log_path: Path,
    last_commit: str | None = None,
    last_location: str | None = None,
) -> dict[str, str]:
    """
    Build the complete context for an agent's session start.

    Returns a dict with:
        - "memory": the agent's accumulated memories
        - "diff": description of changes since last session
        - "location": where the agent starts this session
    """
    # Memory
    memory = build_agent_memory(agent_name, log_path)

    # Diff — what changed while the agent slept
    changes = get_place_diff(place_path, since_commit=last_commit, agent_name=agent_name)
    diff = format_diff_for_agent(changes)

    # Location — where the agent last was, or default
    location = last_location or "here"

    return {
        "memory": memory,
        "diff": diff,
        "location": location,
    }
