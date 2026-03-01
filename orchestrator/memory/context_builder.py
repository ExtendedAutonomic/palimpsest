"""
Context builder for Palimpsest.

Assembles the context an agent receives at the start of each session:
memory + location. That's it. The agent discovers everything else
by perceiving and exploring.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .summariser import build_agent_memory

logger = logging.getLogger(__name__)


def build_session_context(
    agent_name: str,
    log_path: Path,
    last_location: str | None = None,
) -> dict[str, str]:
    """
    Build the complete context for an agent's session start.

    Returns a dict with:
        - "memory": the agent's own reflections
        - "location": where the agent starts this session
    """
    memory = build_agent_memory(agent_name, log_path)
    location = last_location or "here"

    return {
        "memory": memory,
        "location": location,
    }
