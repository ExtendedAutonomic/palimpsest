"""
Tests for note parsing and building — the markdown format that
underpins everything in the place.
"""

from __future__ import annotations

from orchestrator.place.notes import (
    ParsedNote,
    parse_note,
    parse_frontmatter,
    build_frontmatter,
    build_space_note,
    build_thing_note,
)


class TestParseFrontmatter:
    """YAML frontmatter extraction."""

    def test_basic_frontmatter(self):
        text = "---\ntype: space\ncreated_by: claude\n---\nBody text."
        meta, body = parse_frontmatter(text)
        assert meta["type"] == "space"
        assert meta["created_by"] == "claude"
        assert body.strip() == "Body text."

    def test_integer_values(self):
        text = "---\ncreated_session: 5\n---\n"
        meta, body = parse_frontmatter(text)
        assert meta["created_session"] == 5
        assert isinstance(meta["created_session"], int)

    def test_no_frontmatter(self):
        text = "Just some text."
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == "Just some text."

    def test_empty_frontmatter(self):
        text = "---\n---\nBody."
        meta, body = parse_frontmatter(text)
        assert meta == {}


class TestParseNote:
    """Full note parsing — frontmatter + body + sections."""

    def test_parse_space_note(self):
        text = (
            "---\ntype: space\ncreated_by: claude\ncreated_session: 1\n"
            "updated_by: claude\nupdated_session: 1\n---\n"
            "A quiet garden.\n\n"
            "## Connected Spaces\n- [[here]]\n- [[the library]]\n\n"
            "## Things\n- [[a stone]]\n"
        )
        note = parse_note(text)
        assert note.note_type == "space"
        assert "quiet garden" in note.description
        assert note.spaces == ["here", "the library"]
        assert note.things == ["a stone"]

    def test_parse_thing_note(self):
        text = (
            "---\ntype: thing\ncreated_by: claude\ncreated_session: 1\n"
            "updated_by: claude\nupdated_session: 1\n---\n"
            "Grey and smooth, cold to the touch.\n"
        )
        note = parse_note(text)
        assert note.note_type == "thing"
        assert "Grey and smooth" in note.description
        assert note.spaces == []
        assert note.things == []

    def test_parse_space_with_no_connections(self):
        text = (
            "---\ntype: space\ncreated_by: claude\ncreated_session: 1\n"
            "updated_by: claude\nupdated_session: 1\n---\n"
            "An empty room.\n\n"
            "## Connected Spaces\n\n"
            "## Things\n"
        )
        note = parse_note(text)
        assert note.spaces == []
        assert note.things == []

    def test_parse_preserves_raw(self):
        text = "---\ntype: thing\n---\nContent."
        note = parse_note(text)
        assert note.raw == text


class TestBuildNotes:
    """Note construction."""

    def test_build_space_roundtrip(self):
        """Build a space note, parse it, verify all fields survive."""
        fm = {
            "type": "space",
            "created_by": "claude",
            "created_session": 1,
            "updated_by": "claude",
            "updated_session": 1,
        }
        text = build_space_note(
            description="A quiet garden.",
            spaces=["here", "the library"],
            things=["a stone"],
            frontmatter=fm,
        )
        note = parse_note(text)
        assert note.note_type == "space"
        assert "quiet garden" in note.description
        assert note.spaces == ["here", "the library"]
        assert note.things == ["a stone"]
        assert note.frontmatter["created_by"] == "claude"

    def test_build_thing_roundtrip(self):
        """Build a thing note, parse it, verify all fields survive."""
        fm = {
            "type": "thing",
            "created_by": "claude",
            "created_session": 1,
            "updated_by": "claude",
            "updated_session": 1,
        }
        text = build_thing_note("Grey and smooth.", fm)
        note = parse_note(text)
        assert note.note_type == "thing"
        assert "Grey and smooth" in note.description

    def test_build_frontmatter(self):
        text = build_frontmatter({"type": "space", "created_by": "claude"})
        assert text.startswith("---")
        assert text.endswith("---")
        assert "type: space" in text

    def test_empty_description_roundtrip(self):
        """Spaces with empty descriptions should parse cleanly."""
        fm = {"type": "space", "created_by": "place", "created_session": 0,
              "updated_by": "place", "updated_session": 0}
        text = build_space_note("", [], [], fm)
        note = parse_note(text)
        assert note.note_type == "space"
        assert note.description == ""
        assert note.spaces == []
        assert note.things == []


class TestMultipleLinksInSection:
    """Verify wiki link extraction handles various formats."""

    def test_multiple_links_on_separate_lines(self):
        text = (
            "---\ntype: space\n---\nDescription.\n\n"
            "## Connected Spaces\n"
            "- [[here]]\n"
            "- [[the garden]]\n"
            "- [[the deep]]\n\n"
            "## Things\n"
        )
        note = parse_note(text)
        assert note.spaces == ["here", "the garden", "the deep"]
