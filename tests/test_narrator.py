"""
Tests for the narrator agent.

These test everything except the actual API call: prompt loading,
log gathering, input assembly, chapter numbering, and output handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.narrator.narrator import (
    load_narrator_prompt,
    gather_session_logs,
    gather_readable_logs,
    get_previous_entries,
    get_next_chapter_number,
    build_narrator_input,
)
from tests.helpers import make_session_log, write_session_log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def narrator_prompt(tmp_path: Path) -> Path:
    """Create a minimal narrator prompt file."""
    prompt = tmp_path / "narrator_prompt.md"
    prompt.write_text(
        "---\ncreated: 2026-01-01\ntags:\n  - test\n---\n"
        "## Identity\n\nYou are a chronicler.\n",
        encoding="utf-8",
    )
    return prompt


@pytest.fixture
def narrator_prompt_no_frontmatter(tmp_path: Path) -> Path:
    """Create a narrator prompt without YAML frontmatter."""
    prompt = tmp_path / "narrator_prompt.md"
    prompt.write_text(
        "## Identity\n\nYou are a chronicler.\n",
        encoding="utf-8",
    )
    return prompt


@pytest.fixture
def narrator_output(tmp_path: Path) -> Path:
    """Create a narrator output directory."""
    output = tmp_path / "narrator"
    output.mkdir()
    return output


@pytest.fixture
def day_with_logs(log_path: Path) -> datetime:
    """Write session logs for a known day and return that day."""
    write_session_log(log_path, "claude", 1)
    write_session_log(log_path, "claude", 2)
    return datetime(2026, 3, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# load_narrator_prompt
# ---------------------------------------------------------------------------

class TestLoadNarratorPrompt:

    def test_strips_yaml_frontmatter(self, narrator_prompt: Path):
        result = load_narrator_prompt(narrator_prompt)
        assert "created:" not in result
        assert "tags:" not in result
        assert "## Identity" in result

    def test_loads_without_frontmatter(self, narrator_prompt_no_frontmatter: Path):
        result = load_narrator_prompt(narrator_prompt_no_frontmatter)
        assert "## Identity" in result

    def test_raises_if_file_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_narrator_prompt(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# gather_session_logs
# ---------------------------------------------------------------------------

class TestGatherSessionLogs:

    def test_finds_logs_for_target_day(self, log_path: Path, day_with_logs: datetime):
        logs = gather_session_logs(log_path, day_with_logs)
        assert len(logs) == 2

    def test_sorted_by_session_number(self, log_path: Path, day_with_logs: datetime):
        logs = gather_session_logs(log_path, day_with_logs)
        assert logs[0]["session_number"] == 1
        assert logs[1]["session_number"] == 2

    def test_excludes_different_day(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        other_day = datetime(2026, 3, 15, tzinfo=timezone.utc)
        logs = gather_session_logs(log_path, other_day)
        assert len(logs) == 0

    def test_excludes_narrator_directory(self, log_path: Path, day_with_logs: datetime):
        # Create a fake file in the narrator dir
        narrator_dir = log_path / "narrator"
        narrator_dir.mkdir()
        fake_log = make_session_log()
        (narrator_dir / "session_0001.json").write_text(
            json.dumps(fake_log), encoding="utf-8"
        )
        logs = gather_session_logs(log_path, day_with_logs)
        assert len(logs) == 2  # Only the agent logs

    def test_gathers_across_agents(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        write_session_log(log_path, "gemini", 1)
        day = datetime(2026, 3, 1, tzinfo=timezone.utc)
        logs = gather_session_logs(log_path, day)
        assert len(logs) == 2

    def test_empty_log_directory(self, log_path: Path):
        day = datetime(2026, 3, 1, tzinfo=timezone.utc)
        logs = gather_session_logs(log_path, day)
        assert len(logs) == 0


# ---------------------------------------------------------------------------
# gather_readable_logs
# ---------------------------------------------------------------------------

class TestGatherReadableLogs:

    def test_falls_back_to_rendering(self, log_path: Path, day_with_logs: datetime):
        """Without readable/ files, should render from JSON."""
        logs = gather_readable_logs(log_path, day_with_logs)
        assert len(logs) == 2
        assert "# Claude" in logs[0]

    def test_prefers_readable_files(self, log_path: Path, day_with_logs: datetime):
        """If readable/ exists, should use it."""
        readable_dir = log_path / "claude" / "readable"
        readable_dir.mkdir(parents=True)
        (readable_dir / "session_0001.md").write_text(
            "# Custom readable log", encoding="utf-8"
        )
        logs = gather_readable_logs(log_path, day_with_logs)
        # First log should be the custom one
        assert any("Custom readable log" in log for log in logs)


# ---------------------------------------------------------------------------
# get_previous_entries / get_next_chapter_number
# ---------------------------------------------------------------------------

class TestPreviousEntries:

    def test_empty_when_no_entries(self, narrator_output: Path):
        entries = get_previous_entries(narrator_output)
        assert entries == []

    def test_loads_existing_entries(self, narrator_output: Path):
        (narrator_output / "chapter_0001.md").write_text(
            "# Chapter 1: The Beginning\n\nSomething happened.",
            encoding="utf-8",
        )
        entries = get_previous_entries(narrator_output)
        assert len(entries) == 1
        assert entries[0]["chapter"] == 1
        assert entries[0]["title"] == "Chapter 1: The Beginning"

    def test_sorted_by_chapter_number(self, narrator_output: Path):
        (narrator_output / "chapter_0003.md").write_text(
            "# Third\n\nThree.", encoding="utf-8"
        )
        (narrator_output / "chapter_0001.md").write_text(
            "# First\n\nOne.", encoding="utf-8"
        )
        (narrator_output / "chapter_0002.md").write_text(
            "# Second\n\nTwo.", encoding="utf-8"
        )
        entries = get_previous_entries(narrator_output)
        assert [e["chapter"] for e in entries] == [1, 2, 3]

    def test_nonexistent_directory(self, tmp_path: Path):
        entries = get_previous_entries(tmp_path / "nope")
        assert entries == []


class TestNextChapterNumber:

    def test_starts_at_one(self, narrator_output: Path):
        assert get_next_chapter_number(narrator_output) == 1

    def test_increments(self, narrator_output: Path):
        (narrator_output / "chapter_0001.md").write_text("x", encoding="utf-8")
        assert get_next_chapter_number(narrator_output) == 2

    def test_handles_gaps(self, narrator_output: Path):
        (narrator_output / "chapter_0001.md").write_text("x", encoding="utf-8")
        (narrator_output / "chapter_0005.md").write_text("x", encoding="utf-8")
        assert get_next_chapter_number(narrator_output) == 6

    def test_nonexistent_directory(self, tmp_path: Path):
        assert get_next_chapter_number(tmp_path / "nope") == 1


# ---------------------------------------------------------------------------
# build_narrator_input
# ---------------------------------------------------------------------------

class TestBuildNarratorInput:

    def test_includes_session_logs(self):
        result = build_narrator_input(
            readable_logs=["# Session 1\n\nSomething happened."],
            diff_text="Nothing has changed since you were last here.",
            previous_entries=[],
            chapter_number=1,
        )
        assert "# Session 1" in result
        assert "Write Chapter 1." in result

    def test_includes_diff_when_present(self):
        result = build_narrator_input(
            readable_logs=["# Session 1"],
            diff_text="Something new has appeared: The Garden.md",
            previous_entries=[],
            chapter_number=1,
        )
        assert "What changed in the place today" in result
        assert "The Garden.md" in result

    def test_excludes_diff_when_nothing_changed(self):
        result = build_narrator_input(
            readable_logs=["# Session 1"],
            diff_text="Nothing has changed since you were last here.",
            previous_entries=[],
            chapter_number=1,
        )
        assert "What changed in the place today" not in result

    def test_includes_previous_entries(self):
        result = build_narrator_input(
            readable_logs=["# Session 1"],
            diff_text="",
            previous_entries=[{
                "chapter": 1,
                "title": "The Beginning",
                "content": "Something happened on day one.",
            }],
            chapter_number=2,
        )
        assert "Your previous entries" in result
        assert "Chapter 1: The Beginning" in result
        assert "Write Chapter 2." in result

    def test_chapter_number_in_instruction(self):
        result = build_narrator_input(
            readable_logs=["log"],
            diff_text="",
            previous_entries=[],
            chapter_number=7,
        )
        assert "Write Chapter 7." in result
