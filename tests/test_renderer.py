"""
Tests for the session log renderer.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.renderer import render_session_markdown, save_readable_log
from tests.helpers import make_session_log


class TestRenderSessionMarkdown:
    """Rendering session logs to readable markdown."""

    def test_renders_frontmatter(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "agent: claude" in md
        assert "session: 1" in md

    def test_renders_title(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "# Claude — Session 1" in md

    def test_renders_phase_name(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "The Solitary" in md

    def test_renders_tool_calls(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "**perceive**" in md

    def test_renders_reflection(self, tmp_path: Path):
        log_data = make_session_log(reflection="The silence was profound.")
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "## Reflection" in md
        assert "silence was profound" in md

    def test_renders_agent_text(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "I look around." in md

    def test_no_reflection_omits_section(self, tmp_path: Path):
        log_data = make_session_log(reflection="")
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "## Reflection" not in md


    def test_renders_memory_as_compact_reference(self, tmp_path: Path):
        log_data = make_session_log(session_number=2)
        log_data["opening_prompt"] = (
            "## Memory\n\n---\n\nDay 1\n\n"
            "I explored the place.\n\n"
            "You are at: here"
        )
        log_file = tmp_path / "session_0002.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "[[Claude \u2014 Session 1|Day 1]]" in md
        assert "> You are at: here" in md
        # Full memory content should NOT appear
        assert "I explored the place." not in md

    def test_renders_compressed_and_full_memory(self, tmp_path: Path):
        log_data = make_session_log(session_number=7)
        log_data["opening_prompt"] = (
            "## Memory\n\n---\n\n"
            "Days 1\u20133\n\ncompressed stuff\n\n---\n\n"
            "Day 4\n\nfull log 4\n\n---\n\n"
            "Day 5\n\nfull log 5\n\n---\n\n"
            "Day 6\n\nfull log 6\n\n"
            "You are at: the garden"
        )
        log_file = tmp_path / "session_0007.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "Days 1\u20133 (compressed)" in md
        assert "[[Claude \u2014 Session 4|Day 4]]" in md
        assert "[[Claude \u2014 Session 5|Day 5]]" in md
        assert "[[Claude \u2014 Session 6|Day 6]]" in md
        assert "> You are at: the garden" in md
        assert "compressed stuff" not in md
        assert "full log 4" not in md


class TestSaveReadableLog:
    """Saving rendered logs to disk."""

    def test_creates_readable_file(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        output = save_readable_log(log_file)
        assert output.exists()
        assert output.suffix == ".md"
        assert output.name == "session_0001.md"

    def test_creates_readable_directory(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        save_readable_log(log_file)
        assert (tmp_path / "readable").is_dir()

    def test_custom_output_directory(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        custom_dir = tmp_path / "custom_output"
        output = save_readable_log(log_file, output_dir=custom_dir)
        assert output.parent == custom_dir
