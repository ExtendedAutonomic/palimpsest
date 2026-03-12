"""
Tests for the memory system — building agent memory from logs
and the session runner helpers.

Compression tests mock _complete() to verify triggering logic,
frontmatter updates, and the rolling compression flow without spending.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.memory.summariser import (
    build_agent_memory,
    run_memory_compression,
    render_session_log,
    _parse_compressed_frontmatter,
    RECENT_WINDOW,
)
from orchestrator.memory.context_builder import build_session_context
from orchestrator.session_runner import (
    get_next_session_number,
    get_last_location,
    resolve_agent_config,
)

from tests.helpers import write_session_log


# Minimal test config matching the real agents.yaml structure
_TEST_CONFIG = {
    "agents": {
        "defaults": {
            "nudge": "...",
            "founding_prompt": "founding",
            "system_prompt": None,
            "place": "place",
            "extended_thinking": True,
            "active": True,
            "session": {
                "turn_budget": 17,
                "dusk_threshold": 14,
                "max_output_tokens": 4096,
                "context_limit": 180000,
                "cost_limit": 3.00,
            },
            "compression": {
                "enabled": True,
                "recent_window": 2,
                "days_per_week": 7,
            },
        },
        "agents": {
            "claude": {
                "provider": "claude",
                "model": "claude-opus-4-6",
                "start_location": "here",
            },
            "gemini": {
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "start_location": "there",
                "extended_thinking": False,
            },
            "deepseek": {
                "provider": "deepseek",
                "model": "deepseek-v3.2",
                "start_location": "somewhere",
                "extended_thinking": False,
                "active": False,
            },
        },
    },
    "prompts": {
        "founding": "You are: {location}",
    },
}


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


class TestStartLocations:
    """Per-agent starting locations from the agent registry."""

    def test_claude_starts_at_here(self):
        ac = resolve_agent_config("claude", _TEST_CONFIG)
        assert ac["start_location"] == "here"

    def test_gemini_starts_at_there(self):
        ac = resolve_agent_config("gemini", _TEST_CONFIG)
        assert ac["start_location"] == "there"

    def test_deepseek_starts_at_somewhere(self):
        ac = resolve_agent_config("deepseek", _TEST_CONFIG)
        assert ac["start_location"] == "somewhere"

    def test_all_agents_have_start_locations(self):
        for agent in ["claude", "gemini", "deepseek"]:
            ac = resolve_agent_config(agent, _TEST_CONFIG)
            assert "start_location" in ac
            assert ac["start_location"] is not None

    def test_all_start_locations_unique(self):
        locations = [
            resolve_agent_config(a, _TEST_CONFIG)["start_location"]
            for a in ["claude", "gemini", "deepseek"]
        ]
        assert len(locations) == len(set(locations))


class TestStartingSpaceCreation:
    """Auto-creation of starting spaces on first session."""

    def test_starting_space_created_if_missing(self, place_path: Path):
        """Running session 1 for Gemini creates there.md."""
        there = place_path / "there.md"
        assert not there.exists()

        ac = resolve_agent_config("gemini", _TEST_CONFIG)
        start_location = ac["start_location"]
        start_note = place_path / f"{start_location}.md"
        if not start_note.exists():
            start_note.write_text(
                "---\n"
                "type: space\n"
                "created_by: place\n"
                "created_session: 0\n"
                "updated_by: place\n"
                "updated_session: 0\n"
                "---\n",
                encoding="utf-8",
            )

        assert there.exists()
        content = there.read_text(encoding="utf-8")
        assert "type: space" in content
        assert "created_by: place" in content

    def test_existing_space_not_overwritten(self, place_path: Path):
        """If here.md already exists, it's not touched."""
        here = place_path / "here.md"
        original = here.read_text(encoding="utf-8")

        ac = resolve_agent_config("claude", _TEST_CONFIG)
        start_location = ac["start_location"]
        start_note = place_path / f"{start_location}.md"
        if not start_note.exists():
            start_note.write_text("should not happen", encoding="utf-8")

        assert here.read_text(encoding="utf-8") == original


class TestFoundingPromptTemplate:
    """The founding prompt uses the agent's starting location."""

    def test_founding_prompt_with_here(self):
        template = "You are: {location}"
        assert template.format(location="here") == "You are: here"

    def test_founding_prompt_with_there(self):
        template = "You are: {location}"
        assert template.format(location="there") == "You are: there"

    def test_founding_prompt_with_somewhere(self):
        template = "You are: {location}"
        assert template.format(location="somewhere") == "You are: somewhere"


# ---------------------------------------------------------------------------
# Rolling compression tests
# ---------------------------------------------------------------------------

def _mock_complete_result(text: str):
    """Build a mock return value for _complete(): (text, token_counts)."""
    return (text, {"input": 100, "output": 50})


class TestCompressionTrigger:
    """Rolling compression fires at the right time."""

    def test_no_compression_under_window(self, log_path: Path):
        """No compression when sessions <= RECENT_WINDOW."""
        write_session_log(log_path, "claude", 1, reflection="Day one.")
        write_session_log(log_path, "claude", 2, reflection="Day two.")
        result = asyncio.run(run_memory_compression(
            "claude", log_path,
            compressor_model="claude-opus-4-6", compressor_provider="claude",
        ))
        assert result is False

    def test_compression_fires_above_window(self, log_path: Path):
        """Compression triggers when sessions > RECENT_WINDOW."""
        write_session_log(log_path, "claude", 1, reflection="Day one.")
        write_session_log(log_path, "claude", 2, reflection="Day two.")
        write_session_log(log_path, "claude", 3, reflection="Day three.")

        with patch(
            "orchestrator.memory.summariser._complete",
            new=AsyncMock(return_value=_mock_complete_result(
                "### Week 1 (Days 1)\n\nI arrived and sat."
            )),
        ):
            result = asyncio.run(run_memory_compression(
                "claude", log_path,
                compressor_model="claude-opus-4-6", compressor_provider="claude",
            ))

        assert result is True

    def test_no_compression_for_missing_agent(self, log_path: Path):
        result = asyncio.run(run_memory_compression(
            "nonexistent", log_path,
            compressor_model="claude-opus-4-6", compressor_provider="claude",
        ))
        assert result is False


class TestCompressionResults:
    """Compression produces correct output."""

    def test_compressed_through_updated(self, log_path: Path):
        """compressed_through tracks the last compressed session."""
        for i in range(1, 5):
            write_session_log(log_path, "claude", i, reflection=f"Day {i}.")

        with patch(
            "orchestrator.memory.summariser._complete",
            new=AsyncMock(return_value=_mock_complete_result(
                "### Week 1 (Days 1\u20132)\n\nFirst days."
            )),
        ):
            asyncio.run(run_memory_compression(
                "claude", log_path,
                compressor_model="claude-opus-4-6", compressor_provider="claude",
            ))

        compressed_file = log_path / "claude" / "compressed_memory.md"
        assert compressed_file.exists()
        fm, _ = _parse_compressed_frontmatter(
            compressed_file.read_text(encoding="utf-8")
        )
        assert fm["compressed_through"] == 2

    def test_exactly_recent_window_remain(self, log_path: Path):
        """After compression, exactly RECENT_WINDOW sessions are uncompressed."""
        for i in range(1, 6):
            write_session_log(log_path, "claude", i, reflection=f"Day {i}.")

        with patch(
            "orchestrator.memory.summariser._complete",
            new=AsyncMock(return_value=_mock_complete_result(
                "### Week 1 (Days 1\u20133)\n\nFirst three days."
            )),
        ):
            asyncio.run(run_memory_compression(
                "claude", log_path,
                compressor_model="claude-opus-4-6", compressor_provider="claude",
            ))

        compressed_file = log_path / "claude" / "compressed_memory.md"
        fm, _ = _parse_compressed_frontmatter(
            compressed_file.read_text(encoding="utf-8")
        )
        # Sessions 4 and 5 remain uncompressed
        assert fm["compressed_through"] == 3

        # build_agent_memory should show compressed + 2 raw days
        memory = build_agent_memory("claude", log_path)
        assert "Week 1" in memory
        assert "Day 4" in memory
        assert "Day 5" in memory
        assert "Day 3\n" not in memory  # compressed, not raw

    def test_rolling_adds_one_day_at_a_time(self, log_path: Path):
        """With existing compressed memory, each new day is woven in individually."""
        agent_dir = log_path / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        compressed_file = agent_dir / "compressed_memory.md"
        compressed_file.write_text(
            "---\n"
            "type: compressed_memory\n"
            "agent: claude\n"
            "model: claude-opus-4-6\n"
            "compressed_through: 3\n"
            "tokens: 100\n"
            "cost: $0.01\n"
            "updated: 2026-03-08\n"
            "---\n\n"
            "### Week 1 (Days 1\u20133)\n\nFirst three days.",
            encoding="utf-8",
        )

        # Write sessions 4, 5, 6
        for i in range(4, 7):
            write_session_log(log_path, "claude", i, reflection=f"Day {i}.")

        call_count = 0
        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_complete_result(
                f"### Week 1 (Days 1\u2013{3 + call_count})\n\nUpdated memory."
            )

        with patch(
            "orchestrator.memory.summariser._complete",
            new=mock_complete,
        ):
            asyncio.run(run_memory_compression(
                "claude", log_path,
                compressor_model="claude-opus-4-6", compressor_provider="claude",
            ))

        # Should have been called once (day 4 only)
        # Days 5 and 6 remain as raw
        assert call_count == 1

        fm, _ = _parse_compressed_frontmatter(
            compressed_file.read_text(encoding="utf-8")
        )
        assert fm["compressed_through"] == 4

    def test_multiple_days_compressed_sequentially(self, log_path: Path):
        """If multiple days need compressing, each is woven in one at a time."""
        agent_dir = log_path / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        compressed_file = agent_dir / "compressed_memory.md"
        compressed_file.write_text(
            "---\n"
            "type: compressed_memory\n"
            "agent: claude\n"
            "model: claude-opus-4-6\n"
            "compressed_through: 3\n"
            "tokens: 100\n"
            "cost: $0.01\n"
            "updated: 2026-03-08\n"
            "---\n\n"
            "### Week 1 (Days 1\u20133)\n\nFirst three days.",
            encoding="utf-8",
        )

        # Write sessions 4 through 8: 5 uncompressed, need to compress 3
        for i in range(4, 9):
            write_session_log(log_path, "claude", i, reflection=f"Day {i}.")

        call_count = 0
        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_complete_result(
                f"### Week 1 (Days 1\u2013{3 + call_count})\n\nUpdated memory."
            )

        with patch(
            "orchestrator.memory.summariser._complete",
            new=mock_complete,
        ):
            asyncio.run(run_memory_compression(
                "claude", log_path,
                compressor_model="claude-opus-4-6", compressor_provider="claude",
            ))

        # 3 days to compress (4, 5, 6), each one API call
        assert call_count == 3

        fm, _ = _parse_compressed_frontmatter(
            compressed_file.read_text(encoding="utf-8")
        )
        assert fm["compressed_through"] == 6


class TestWeekStructuredMemory:
    """build_agent_memory works with the week-headed compressed format."""

    def test_week_headings_in_output(self, log_path: Path):
        agent_dir = log_path / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        compressed_file = agent_dir / "compressed_memory.md"
        compressed_file.write_text(
            "---\n"
            "type: compressed_memory\n"
            "agent: claude\n"
            "compressed_through: 7\n"
            "---\n\n"
            "### Week 1 (Days 1\u20137)\n\nFirst week summary.",
            encoding="utf-8",
        )

        write_session_log(log_path, "claude", 8, reflection="Day eight.")
        write_session_log(log_path, "claude", 9, reflection="Day nine.")

        memory = build_agent_memory("claude", log_path)
        assert "Week 1 (Days 1\u20137)" in memory
        assert "First week summary" in memory
        assert "Day 8" in memory
        assert "Day 9" in memory

    def test_multi_week_compressed_memory(self, log_path: Path):
        agent_dir = log_path / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        compressed_file = agent_dir / "compressed_memory.md"
        compressed_file.write_text(
            "---\n"
            "type: compressed_memory\n"
            "agent: claude\n"
            "compressed_through: 10\n"
            "---\n\n"
            "### Week 1 (Days 1\u20137)\n\nFirst week.\n\n"
            "### Week 2 (Days 8\u201310)\n\nSecond week started.",
            encoding="utf-8",
        )

        write_session_log(log_path, "claude", 11, reflection="Day eleven.")
        write_session_log(log_path, "claude", 12, reflection="Day twelve.")

        memory = build_agent_memory("claude", log_path)
        assert "Week 1" in memory
        assert "Week 2" in memory
        assert "Day 11" in memory
        assert "Day 12" in memory


class TestRenderSessionLog:
    """Session log rendering distinguishes voices."""

    def test_nudge_is_bracketed(self):
        """Nudges use [response: ...] format in agent memory,
        consistent with other bracketed non-agent content."""
        log = {
            "turns": [
                {
                    "agent_text": "...",
                    "thinking": None,
                    "nudge": "...",
                    "tool_calls": [],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "[Response: ...]" in rendered
        # Agent's ellipsis should be prefixed with "You:" not bracketed
        assert "You: ..." in rendered

    def test_tool_result_is_blockquoted(self):
        log = {
            "turns": [
                {
                    "agent_text": "I look.",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "perceive",
                            "arguments": {},
                            "result": "You are here.",
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "> You are here." in rendered

    def test_natural_action_for_perceive(self):
        """Successful perceive shows *You perceive.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "perceive",
                            "arguments": {},
                            "result": "here",
                            "success": True,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You perceive.*" in rendered
        assert "perceive()" not in rendered

    def test_natural_action_for_alter_with_rename(self):
        """Successful alter with rename shows arrow notation."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "alter",
                            "arguments": {"what": "the first dialogue", "name": "the memory"},
                            "result": "What was called the first dialogue is now called the memory.",
                            "success": True,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You alter the first dialogue \u2192 the memory.*" in rendered
        assert "alter(" not in rendered

    def test_natural_action_for_alter_description_only(self):
        """Successful alter without rename shows no arrow."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "alter",
                            "arguments": {"what": "a spark", "description": "a steady flame"},
                            "result": "a spark is different now. a steady flame",
                            "success": True,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You alter a spark.*" in rendered
        assert "\u2192" not in rendered

    def test_natural_action_for_create(self):
        """Successful create shows action line + world response."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "create",
                            "arguments": {"name": "a spark", "description": "tiny light"},
                            "result": "a spark is here. tiny light",
                            "success": True,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You create a spark.*" in rendered
        assert "> a spark is here. tiny light" in rendered

    def test_natural_action_for_go(self):
        """Successful go shows *You go to X.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "go",
                            "arguments": {"where": "the garden"},
                            "result": "You are now at the garden.",
                            "success": True,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You go to the garden.*" in rendered
        assert "go(" not in rendered

    def test_attempt_language_on_alter_failure(self):
        """Failed alter shows *You try to alter X.* not *You alter X.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "alter",
                            "arguments": {"what": "another whisper", "name": "the memory of the first dialogue"},
                            "result": 'Something called "the memory of the first dialogue" already exists.',
                            "success": False,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You try to alter another whisper \u2192 the memory of the first dialogue.*" in rendered
        assert "*You alter another whisper" not in rendered

    def test_attempt_language_on_create_failure(self):
        """Failed create shows *You try to create X.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "create",
                            "arguments": {"name": "the void", "description": "emptiness"},
                            "result": 'Something called "the void" already exists.',
                            "success": False,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You try to create the void.*" in rendered

    def test_attempt_language_on_go_failure(self):
        """Failed go shows *You try to go to X.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "go",
                            "arguments": {"where": "the mountain"},
                            "result": 'There is no space called "the mountain" connected to this space.',
                            "success": False,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You try to go to the mountain.*" in rendered
        assert "*You go to the mountain.*" not in rendered

    def test_attempt_language_on_examine_failure(self):
        """Failed examine shows *You try to examine X.*."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "examine",
                            "arguments": {"what": "the lost thing"},
                            "result": 'There is nothing called "the lost thing" here.',
                            "success": False,
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You try to examine the lost thing.*" in rendered
        assert "*You examine the lost thing.*" not in rendered

    def test_old_logs_without_success_default_true(self):
        """Logs without the success field default to declarative voice."""
        log = {
            "turns": [
                {
                    "agent_text": "",
                    "thinking": None,
                    "nudge": None,
                    "tool_calls": [
                        {
                            "tool": "perceive",
                            "arguments": {},
                            "result": "here",
                            "error": None,
                        }
                    ],
                }
            ],
            "dusk_prompt": None,
            "dusk_action": None,
            "reflect_prompt": None,
            "reflection": None,
        }
        rendered = render_session_log(log)
        assert "*You perceive.*" in rendered
        assert "try to" not in rendered
