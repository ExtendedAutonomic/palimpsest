"""
Tests for the experimenter blog system.

Tests everything except the actual API call: prompt loading,
log gathering, narrator chapter loading, design docs, input
assembly, post numbering, and output handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.experimenter.experimenter import (
    load_experimenter_prompt,
    gather_session_logs_range,
    gather_readable_logs_range,
    gather_narrator_chapters,
    gather_cost_summary,
    get_previous_posts,
    get_next_post_number,
    load_design_docs,
    build_experimenter_input,
)
from tests.helpers import make_session_log, write_session_log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def experimenter_prompt(tmp_path: Path) -> Path:
    """Create a minimal experimenter prompt file."""
    prompt = tmp_path / "experimenter_prompt.md"
    prompt.write_text(
        "---\ncreated: 2026-01-01\ntags:\n  - test\n---\n"
        "## Purpose\n\nA blog about running Palimpsest.\n",
        encoding="utf-8",
    )
    return prompt


@pytest.fixture
def experimenter_prompt_no_frontmatter(tmp_path: Path) -> Path:
    """Create a prompt without YAML frontmatter."""
    prompt = tmp_path / "experimenter_prompt.md"
    prompt.write_text(
        "## Purpose\n\nA blog about running Palimpsest.\n",
        encoding="utf-8",
    )
    return prompt


@pytest.fixture
def experimenter_output(tmp_path: Path) -> Path:
    """Create an experimenter output directory."""
    output = tmp_path / "experimenter"
    output.mkdir()
    return output


@pytest.fixture
def narrator_output(tmp_path: Path) -> Path:
    """Create a narrator output directory with sample chapters."""
    output = tmp_path / "narrator"
    output.mkdir()
    (output / "chapter_0001.md").write_text(
        "# The Compass Points Down\n\nI watch them perceive the emptiness.",
        encoding="utf-8",
    )
    (output / "chapter_0002.md").write_text(
        "# What the Light Revealed\n\nThe garden grows.",
        encoding="utf-8",
    )
    return output


@pytest.fixture
def multi_day_logs(log_path: Path) -> Path:
    """Write session logs across multiple days."""
    # Day 1: sessions 1 and 2
    write_session_log(log_path, "claude", 1)
    write_session_log(log_path, "claude", 2)

    # Day 2: session 3 (different date)
    agent_dir = log_path / "claude"
    log_data = make_session_log(agent_name="claude", session_number=3)
    log_data["start_time"] = "2026-03-02T10:00:00+00:00"
    (agent_dir / "session_0003.json").write_text(
        json.dumps(log_data, indent=2), encoding="utf-8"
    )
    return log_path


# ---------------------------------------------------------------------------
# load_experimenter_prompt
# ---------------------------------------------------------------------------

class TestLoadExperimenterPrompt:

    def test_strips_yaml_frontmatter(self, experimenter_prompt: Path):
        result = load_experimenter_prompt(experimenter_prompt)
        assert "created:" not in result
        assert "## Purpose" in result

    def test_loads_without_frontmatter(self, experimenter_prompt_no_frontmatter: Path):
        result = load_experimenter_prompt(experimenter_prompt_no_frontmatter)
        assert "## Purpose" in result

    def test_raises_if_file_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_experimenter_prompt(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# gather_session_logs_range
# ---------------------------------------------------------------------------

class TestGatherSessionLogsRange:

    def test_gathers_all_without_filters(self, multi_day_logs: Path):
        logs = gather_session_logs_range(multi_day_logs)
        assert len(logs) == 3

    def test_filters_by_since(self, multi_day_logs: Path):
        since = datetime(2026, 3, 2, tzinfo=timezone.utc)
        logs = gather_session_logs_range(multi_day_logs, since=since)
        assert len(logs) == 1
        assert logs[0]["session_number"] == 3

    def test_filters_by_until(self, multi_day_logs: Path):
        until = datetime(2026, 3, 1, 23, 59, 59, tzinfo=timezone.utc)
        logs = gather_session_logs_range(multi_day_logs, until=until)
        assert len(logs) == 2

    def test_filters_by_session_number(self, multi_day_logs: Path):
        logs = gather_session_logs_range(multi_day_logs, sessions=(2,))
        assert len(logs) == 1
        assert logs[0]["session_number"] == 2

    def test_filters_by_agent(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        write_session_log(log_path, "gemini", 1)
        logs = gather_session_logs_range(log_path, agent="gemini")
        assert len(logs) == 1
        assert logs[0]["agent_name"] == "gemini"

    def test_excludes_narrator_and_experimenter_dirs(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        # Create fake logs in excluded dirs
        for name in ("narrator", "experimenter"):
            d = log_path / name
            d.mkdir()
            (d / "session_0001.json").write_text(
                json.dumps(make_session_log()), encoding="utf-8"
            )
        logs = gather_session_logs_range(log_path)
        assert len(logs) == 1

    def test_empty_log_directory(self, log_path: Path):
        logs = gather_session_logs_range(log_path)
        assert len(logs) == 0

    def test_sorted_by_session_number(self, multi_day_logs: Path):
        logs = gather_session_logs_range(multi_day_logs)
        numbers = [l["session_number"] for l in logs]
        assert numbers == sorted(numbers)

    def test_combined_since_and_until(self, multi_day_logs: Path):
        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        until = datetime(2026, 3, 1, 23, 59, 59, tzinfo=timezone.utc)
        logs = gather_session_logs_range(multi_day_logs, since=since, until=until)
        assert len(logs) == 2


# ---------------------------------------------------------------------------
# gather_readable_logs_range
# ---------------------------------------------------------------------------

class TestGatherReadableLogsRange:

    def test_falls_back_to_rendering(self, multi_day_logs: Path):
        logs = gather_readable_logs_range(multi_day_logs)
        assert len(logs) == 3
        assert "# Claude" in logs[0]

    def test_prefers_readable_files(self, multi_day_logs: Path):
        readable_dir = multi_day_logs / "claude" / "readable"
        readable_dir.mkdir(parents=True)
        (readable_dir / "session_0001.md").write_text(
            "# Custom readable", encoding="utf-8"
        )
        logs = gather_readable_logs_range(multi_day_logs)
        assert any("Custom readable" in log for log in logs)

    def test_filters_by_agent(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        write_session_log(log_path, "gemini", 1)
        logs = gather_readable_logs_range(log_path, agent="claude")
        assert len(logs) == 1


# ---------------------------------------------------------------------------
# gather_narrator_chapters
# ---------------------------------------------------------------------------

class TestGatherNarratorChapters:

    def test_loads_all_chapters(self, narrator_output: Path):
        chapters = gather_narrator_chapters(narrator_output)
        assert len(chapters) == 2

    def test_parses_title(self, narrator_output: Path):
        chapters = gather_narrator_chapters(narrator_output)
        assert chapters[0]["title"] == "The Compass Points Down"

    def test_sorted_by_chapter_number(self, narrator_output: Path):
        chapters = gather_narrator_chapters(narrator_output)
        assert chapters[0]["chapter"] == 1
        assert chapters[1]["chapter"] == 2

    def test_filters_by_chapter_number(self, narrator_output: Path):
        chapters = gather_narrator_chapters(narrator_output, chapters=(2,))
        assert len(chapters) == 1
        assert chapters[0]["chapter"] == 2

    def test_empty_directory(self, tmp_path: Path):
        empty = tmp_path / "empty_narrator"
        empty.mkdir()
        chapters = gather_narrator_chapters(empty)
        assert chapters == []

    def test_nonexistent_directory(self, tmp_path: Path):
        chapters = gather_narrator_chapters(tmp_path / "nope")
        assert chapters == []


# ---------------------------------------------------------------------------
# get_previous_posts / get_next_post_number
# ---------------------------------------------------------------------------

class TestPreviousPosts:

    def test_empty_when_no_posts(self, experimenter_output: Path):
        posts = get_previous_posts(experimenter_output)
        assert posts == []

    def test_loads_existing_posts(self, experimenter_output: Path):
        (experimenter_output / "post_0001.md").write_text(
            "# What Happens When You Tell an AI\n\nSo I built a thing.",
            encoding="utf-8",
        )
        posts = get_previous_posts(experimenter_output)
        assert len(posts) == 1
        assert posts[0]["number"] == 1
        assert "What Happens" in posts[0]["title"]

    def test_sorted_by_number(self, experimenter_output: Path):
        (experimenter_output / "post_0003.md").write_text(
            "# Third\n\nThree.", encoding="utf-8"
        )
        (experimenter_output / "post_0001.md").write_text(
            "# First\n\nOne.", encoding="utf-8"
        )
        posts = get_previous_posts(experimenter_output)
        assert [p["number"] for p in posts] == [1, 3]

    def test_nonexistent_directory(self, tmp_path: Path):
        posts = get_previous_posts(tmp_path / "nope")
        assert posts == []


class TestNextPostNumber:

    def test_starts_at_one(self, experimenter_output: Path):
        assert get_next_post_number(experimenter_output) == 1

    def test_increments(self, experimenter_output: Path):
        (experimenter_output / "post_0001.md").write_text("x", encoding="utf-8")
        assert get_next_post_number(experimenter_output) == 2

    def test_handles_gaps(self, experimenter_output: Path):
        (experimenter_output / "post_0001.md").write_text("x", encoding="utf-8")
        (experimenter_output / "post_0005.md").write_text("x", encoding="utf-8")
        assert get_next_post_number(experimenter_output) == 6

    def test_nonexistent_directory(self, tmp_path: Path):
        assert get_next_post_number(tmp_path / "nope") == 1


# ---------------------------------------------------------------------------
# load_design_docs
# ---------------------------------------------------------------------------

class TestLoadDesignDocs:

    def test_loads_docs_stripping_frontmatter(self, tmp_path: Path):
        doc = tmp_path / "Palimpsest.md"
        doc.write_text(
            "---\ncreated: 2026-01-01\n---\n### Premise\n\nThe experiment.",
            encoding="utf-8",
        )
        result = load_design_docs([doc])
        assert "### Palimpsest" in result
        assert "The experiment." in result
        assert "created: 2026" not in result

    def test_skips_missing_docs(self, tmp_path: Path):
        result = load_design_docs([tmp_path / "nope.md"])
        assert result == ""

    def test_loads_multiple(self, tmp_path: Path):
        for name in ("Doc A", "Doc B"):
            (tmp_path / f"{name}.md").write_text(
                f"Content of {name}", encoding="utf-8"
            )
        result = load_design_docs([
            tmp_path / "Doc A.md", tmp_path / "Doc B.md"
        ])
        assert "Doc A" in result
        assert "Doc B" in result


# ---------------------------------------------------------------------------
# gather_cost_summary
# ---------------------------------------------------------------------------

class TestGatherCostSummary:

    def test_calculates_costs(self, log_path: Path):
        write_session_log(log_path, "claude", 1)
        config = {
            "costs": {
                "pricing": {
                    "opus": {"input": 5.0, "output": 25.0},
                },
                "models": {"claude": "opus"},
                "budget": {"total_cap": 200},
            }
        }
        result = gather_cost_summary(log_path, config)
        assert "claude" in result
        assert "$" in result
        assert "Total" in result

    def test_empty_logs(self, log_path: Path):
        config = {"costs": {"pricing": {}, "models": {}, "budget": {"total_cap": 200}}}
        result = gather_cost_summary(log_path, config)
        assert "Total" in result


# ---------------------------------------------------------------------------
# build_experimenter_input
# ---------------------------------------------------------------------------

class TestBuildExperimenterInput:

    def _build(self, **kwargs):
        """Helper with sensible defaults for all required params."""
        defaults = dict(
            readable_logs=["log"],
            narrator_chapters=[],
            previous_posts=[],
            design_docs="",
            cost_summary="",
            post_number=1,
        )
        defaults.update(kwargs)
        return build_experimenter_input(**defaults)

    def test_includes_session_logs(self):
        result = self._build(
            readable_logs=["# Session 1\n\nThe agent explored."],
            cost_summary="Total: $0.50 / $200.00",
        )
        assert "# Session 1" in result
        assert "Write Post 1." in result

    def test_includes_topic_when_provided(self):
        result = self._build(topic="the founding prompt evolution")
        assert "the founding prompt evolution" in result

    def test_default_topic_when_none(self):
        # Post 2 with previous posts avoids first-post logic
        result = self._build(
            post_number=2,
            previous_posts=[{"number": 1, "title": "x", "content": "x"}],
        )
        assert "whatever is most interesting" in result

    def test_first_post_includes_intro_instruction(self):
        result = self._build(post_number=1)
        assert "Introduce the experiment" in result

    def test_first_post_with_topic(self):
        result = self._build(post_number=1, topic="the founding prompt")
        assert "Introduce the experiment" in result
        assert "the founding prompt" in result

    def test_subsequent_post_no_intro(self):
        result = self._build(
            post_number=2,
            previous_posts=[{"number": 1, "title": "x", "content": "x"}],
        )
        assert "Introduce the experiment" not in result

    def test_includes_narrator_chapters(self):
        result = self._build(
            narrator_chapters=[{
                "chapter": 1,
                "title": "The Compass Points Down",
                "content": "I watch them perceive the emptiness.",
            }],
        )
        assert "Narrator's chapters" in result
        assert "The Compass Points Down" in result

    def test_includes_previous_posts(self):
        result = self._build(
            previous_posts=[{
                "number": 1,
                "title": "What Happens When You Tell an AI",
                "content": "So I built a thing.",
            }],
            post_number=2,
        )
        assert "Your previous posts" in result
        assert "What Happens" in result
        assert "Write Post 2." in result

    def test_includes_design_docs(self):
        result = self._build(
            design_docs="### Palimpsest\n\nThe experiment.",
        )
        assert "Experiment design" in result
        assert "The experiment." in result

    def test_includes_cost_summary(self):
        result = self._build(
            cost_summary="claude: 3 sessions, 5,100 tokens, $0.50",
        )
        assert "Cost summary" in result
        assert "$0.50" in result

    def test_post_number_in_instruction(self):
        result = self._build(
            post_number=4,
            previous_posts=[{"number": 3, "title": "x", "content": "x"}],
        )
        assert "Write Post 4." in result
