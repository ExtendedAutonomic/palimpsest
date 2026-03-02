"""
Tests for the memory system — building agent memory from logs
and the session runner helpers.

Memory compression tests are limited to what we can test without
hitting the Anthropic API (the compression itself calls Claude).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.memory.summariser import build_agent_memory
from orchestrator.memory.context_builder import build_session_context
from orchestrator.session_runner import get_next_session_number, get_last_location

from tests.helpers import write_session_log


class TestBuildAgentMemory:
    """Building the memory block from session logs."""

    def test_no_logs_returns_empty(self, log_path: Path):
        result = build_agent_memory("claude", log_path)
        assert result == ""

    def test_single_session_memory(self, log_path: Path):
        write_session_log(log_path, "claude", 1, reflection="The place is quiet.")
        result = build_agent_memory("claude", log_path)
        assert "## Memory" in result
        assert "Day 1" in result
        assert "The place is quiet." in result

    def test_multiple_sessions_all_included(self, log_path: Path):
        write_session_log(log_path, "claude", 1, reflection="Day one was still.")
        write_session_log(log_path, "claude", 2, reflection="Day two I explored.")
        write_session_log(log_path, "claude", 3, reflection="Day three I built.")
        result = build_agent_memory("claude", log_path)
        assert "Day 1" in result
        assert "Day 2" in result
        assert "Day 3" in result
        assert "Day one was still." in result
        assert "Day three I built." in result

    def test_session_without_reflection_still_included(self, log_path: Path):
        """Sessions without reflections are still included — they have turns."""
        write_session_log(log_path, "claude", 1, reflection="")
        write_session_log(log_path, "claude", 2, reflection="I noticed something.")
        result = build_agent_memory("claude", log_path)
        assert "Day 1" in result
        assert "Day 2" in result
        assert "I look around." in result  # From the turn in session 1
        assert "I noticed something." in result

    def test_different_agents_separate(self, log_path: Path):
        """Each agent only sees its own memory."""
        write_session_log(log_path, "claude", 1, reflection="I am Claude.")
        write_session_log(log_path, "gemini", 1, reflection="I am Gemini.")
        claude_memory = build_agent_memory("claude", log_path)
        gemini_memory = build_agent_memory("gemini", log_path)
        assert "I am Claude." in claude_memory
        assert "I am Gemini." not in claude_memory
        assert "I am Gemini." in gemini_memory

    def test_compressed_memory_included(self, log_path: Path):
        """If a compressed memory file exists, it's included in the output."""
        agent_dir = log_path / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)

        compressed = agent_dir / "compressed_memory.md"
        compressed.write_text(
            "### Days 1\u20135\n\nI explored and built things.\n\n"
            "<!-- compressed_through: 5 -->\n",
            encoding="utf-8",
        )

        # Write sessions 6 and 7
        write_session_log(log_path, "claude", 6, reflection="Day six.")
        write_session_log(log_path, "claude", 7, reflection="Day seven.")

        result = build_agent_memory("claude", log_path)
        assert "Days 1\u20135" in result
        assert "explored and built" in result
        assert "Day 6" in result
        assert "Day 7" in result
        # Sessions 1-5 should not appear as individual days
        assert "Day 1\n" not in result


class TestBuildSessionContext:
    """The context builder assembles memory + location."""

    def test_first_session_empty_memory(self, log_path: Path):
        context = build_session_context("claude", log_path, last_location=None)
        assert context["memory"] == ""
        assert context["location"] == "here"

    def test_with_last_location(self, log_path: Path):
        context = build_session_context("claude", log_path, last_location="the garden")
        assert context["location"] == "the garden"

    def test_with_existing_logs(self, log_path: Path):
        write_session_log(log_path, "claude", 1, reflection="First day.")
        context = build_session_context(
            "claude", log_path, last_location="the garden"
        )
        assert "First day." in context["memory"]
        assert context["location"] == "the garden"


class TestSessionRunnerHelpers:
    """Session numbering and location tracking."""

    def test_next_session_no_logs(self, log_path: Path):
        assert get_next_session_number("claude", log_path) == 1

    def test_next_session_increments(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        assert get_next_session_number("claude", log_path) == 2

    def test_next_session_with_gaps(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        write_session_log(log_path, "claude", 5)
        assert get_next_session_number("claude", log_path) == 6

    def test_last_location_no_logs(self, log_path: Path):
        assert get_last_location("claude", log_path) is None

    def test_last_location_from_log(self, log_path: Path):
        write_session_log(log_path, "claude", 1, location_end="the garden")
        assert get_last_location("claude", log_path) == "the garden"

    def test_last_location_uses_most_recent(self, log_path: Path):
        write_session_log(log_path, "claude", 1, location_end="the garden")
        write_session_log(log_path, "claude", 2, location_end="the deep")
        assert get_last_location("claude", log_path) == "the deep"
