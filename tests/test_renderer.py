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
