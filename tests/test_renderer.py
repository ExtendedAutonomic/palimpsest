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
        assert "*You perceive.*" in md

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
        log_data = make_session_log(session_number=2, reflection="")
        log_data["opening_prompt"] = (
            "## Memory\n\n---\n\n### Day 1\n\n"
            "I explored the place.\n\n"
            "You are at: here"
        )
        log_file = tmp_path / "session_0002.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "[[logs/claude/obsidian_logs/session_0001|Day 1]]" in md
        assert "> You are at: here" in md
        # Full memory content should NOT appear
        assert "I explored the place." not in md

    def test_renders_compressed_and_full_memory(self, tmp_path: Path):
        log_data = make_session_log(session_number=7)
        log_data["opening_prompt"] = (
            "## Memory\n\n---\n\n"
            "### Days 1\u20133\n\ncompressed stuff\n\n---\n\n"
            "### Day 4\n\nfull log 4\n\n---\n\n"
            "### Day 5\n\nfull log 5\n\n---\n\n"
            "### Day 6\n\nfull log 6\n\n"
            "You are at: the garden"
        )
        log_file = tmp_path / "session_0007.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "[[logs/claude/compressed_memory|Days 1\u20133 (compressed)]]" in md
        assert "[[logs/claude/obsidian_logs/session_0004|Day 4]]" in md
        assert "[[logs/claude/obsidian_logs/session_0005|Day 5]]" in md
        assert "[[logs/claude/obsidian_logs/session_0006|Day 6]]" in md
        assert "> You are at: the garden" in md
        assert "compressed stuff" not in md
        assert "full log 4" not in md


    def test_renders_week_format_compressed_memory(self, tmp_path: Path):
        log_data = make_session_log(session_number=11)
        log_data["opening_prompt"] = (
            "## Memory\n\n---\n\n"
            "### Week 1 (Days 1\u20137)\n\nFirst week summary.\n\n"
            "### Week 2 (Days 8)\n\nDay eight.\n\nDay 8.\n\n---\n\n"
            "### Day 9\n\nfull log 9\n\n---\n\n"
            "### Day 10\n\nfull log 10\n\n"
            "You are at: here"
        )
        log_file = tmp_path / "session_0011.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        md = render_session_markdown(log_file)
        assert "[[logs/claude/compressed_memory|Days 1\u20138 (compressed)]]" in md
        assert "[[logs/claude/obsidian_logs/session_0009|Day 9]]" in md
        assert "[[logs/claude/obsidian_logs/session_0010|Day 10]]" in md
        assert "first week summary" not in md.lower()  # compressed body not shown
        # "Day 8" from inside compressed memory should not appear as raw link
        assert "session_0008" not in md


class TestSaveReadableLog:
    """Saving rendered logs to disk."""

    def test_creates_readable_file(self, tmp_path: Path):
        log_data = make_session_log()
        json_dir = tmp_path / "json"
        json_dir.mkdir()
        log_file = json_dir / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        output = save_readable_log(log_file)
        assert output.exists()
        assert output.suffix == ".md"
        assert output.name == "session_0001.md"

    def test_creates_obsidian_logs_directory(self, tmp_path: Path):
        log_data = make_session_log()
        json_dir = tmp_path / "json"
        json_dir.mkdir()
        log_file = json_dir / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        save_readable_log(log_file)
        assert (tmp_path / "obsidian_logs").is_dir()

    def test_custom_output_directory(self, tmp_path: Path):
        log_data = make_session_log()
        log_file = tmp_path / "session_0001.json"
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        custom_dir = tmp_path / "custom_output"
        output = save_readable_log(log_file, output_dir=custom_dir)
        assert output.parent == custom_dir
