"""
Shared test helpers for Palimpsest tests.

Fixtures live in conftest.py (auto-discovered by pytest).
Helper functions live here (importable by test modules).
"""

from __future__ import annotations

import json
from pathlib import Path


def make_session_log(
    agent_name: str = "claude",
    session_number: int = 1,
    reflection: str = "I explored the place.",
    location_start: str = "here",
    location_end: str = "here",
    action_count: int = 3,
) -> dict:
    """Create a minimal valid session log dict for testing."""
    return {
        "agent_name": agent_name,
        "session_number": session_number,
        "phase": 1,
        "start_time": "2026-03-01T10:00:00+00:00",
        "end_time": "2026-03-01T10:15:00+00:00",
        "location_start": location_start,
        "location_end": location_end,
        "opening_prompt": "There is a place. You are here.",
        "system_prompt": "When you act, describe what you are doing.",
        "action_count": action_count,
        "reflection": reflection,
        "dusk_prompt": None,
        "reflect_prompt": None,
        "tokens": {"input": 1000, "output": 500},
        "turns": [
            {
                "agent_text": "I look around.",
                "thinking": None,
                "tool_calls": [
                    {
                        "tool": "perceive",
                        "arguments": {},
                        "result": "This space is empty.",
                        "error": None,
                        "timestamp": "2026-03-01T10:01:00+00:00",
                    }
                ],
                "timestamp": "2026-03-01T10:01:00+00:00",
            }
        ],
    }


def write_session_log(log_path: Path, agent_name: str, session_number: int, **kwargs) -> Path:
    """Write a session log file and return its path."""
    agent_dir = log_path / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)

    log_data = make_session_log(
        agent_name=agent_name,
        session_number=session_number,
        **kwargs,
    )
    log_file = agent_dir / f"session_{session_number:04d}.json"
    log_file.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
    return log_file
