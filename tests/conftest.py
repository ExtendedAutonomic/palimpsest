"""
Shared fixtures for Palimpsest tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.place import PlaceInterface
from orchestrator.place.notes import build_space_note


@pytest.fixture
def place_path(tmp_path: Path) -> Path:
    """Create a temporary place directory with the founding space."""
    place = tmp_path / "place"
    place.mkdir()

    here = place / "here.md"
    here.write_text(
        build_space_note(
            description="",
            spaces=[],
            things=[],
            frontmatter={
                "type": "space",
                "created_by": "place",
                "created_session": 0,
                "updated_by": "place",
                "updated_session": 0,
            },
        ),
        encoding="utf-8",
    )
    return place


@pytest.fixture
def place(place_path: Path) -> PlaceInterface:
    """A PlaceInterface pointed at a fresh temporary place."""
    p = PlaceInterface(place_path, agent_name="test-agent", session_number=1)
    p.current_location = "here"
    return p


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    """Create a temporary log directory."""
    logs = tmp_path / "logs"
    logs.mkdir()
    return logs
