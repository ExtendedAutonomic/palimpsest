"""
Integration tests for security — path traversal and name sanitisation.

These tests verify that agents cannot escape the place directory,
regardless of what names they try to use.

Note: the raw place methods (venture, create, go) raise ValueError
for bad names. The execute_tool dispatch catches these and returns
"Something prevented you." — so in practice agents see a gentle
failure, not an exception.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.place import PlaceInterface


class TestNameSanitisation:
    """Names with forbidden characters are rejected."""

    @pytest.mark.parametrize("bad_name", [
        "../escape",
        "..\\escape",
        "path/traversal",
        "path\\traversal",
        "[[wiki]]",
        "has|pipe",
        "has#hash",
        ".hidden",
        "\x00null",
        "",
        "   ",
    ])
    def test_venture_rejects_bad_names(self, place: PlaceInterface, bad_name: str):
        with pytest.raises(ValueError):
            place.venture(bad_name, "Bad place.")
        assert place.current_location == "here"

    @pytest.mark.parametrize("bad_name", [
        "../escape",
        "..\\escape",
        "path/traversal",
        ".hidden",
    ])
    def test_create_rejects_bad_names(self, place: PlaceInterface, bad_name: str):
        with pytest.raises(ValueError):
            place.create(bad_name, "Bad thing.")

    @pytest.mark.parametrize("bad_name", [
        "../escape",
        "path/traversal",
        ".hidden",
    ])
    def test_go_rejects_bad_names(self, place: PlaceInterface, bad_name: str):
        with pytest.raises(ValueError):
            place.go(bad_name)

    def test_execute_tool_catches_bad_names(self, place: PlaceInterface):
        """execute_tool wraps the ValueError into a gentle string response."""
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(
            tool=ToolName.VENTURE,
            arguments={"name": "../escape", "description": "Bad."},
        )
        result = place.execute_tool(tc)
        assert "prevented" in result.lower() or "not possible" in result.lower()
        assert tc.error is not None


class TestResolvedPathSecurity:
    """
    Defence-in-depth: even if a name passes character sanitisation,
    the resolved path must stay within the place directory.
    """

    def test_note_path_stays_within_place(self, place: PlaceInterface, place_path: Path):
        path = place._note_path("valid name")
        assert path.is_relative_to(place_path)

    def test_note_path_rejects_traversal(self, place: PlaceInterface):
        """Direct path traversal is caught by both sanitisation and resolution."""
        with pytest.raises(ValueError):
            place._note_path("../escape")

    def test_names_with_spaces_are_fine(self, place: PlaceInterface, place_path: Path):
        """Normal names with spaces, capitals, etc. should work."""
        path = place._note_path("The Great Hall")
        assert path.is_relative_to(place_path)
        assert path.name == "The Great Hall.md"

    def test_unicode_names_are_fine(self, place: PlaceInterface, place_path: Path):
        """Unicode names should work — agents might get creative."""
        path = place._note_path("庭園")
        assert path.is_relative_to(place_path)


class TestNoDeletion:
    """
    One-way creation — nothing can be deleted.
    The place has no delete capability by design.
    """

    def test_no_delete_method_exists(self, place: PlaceInterface):
        """PlaceInterface should not have any delete/remove/destroy method."""
        dangerous_names = ["delete", "remove", "destroy", "unlink", "erase"]
        for name in dangerous_names:
            assert not hasattr(place, name), f"PlaceInterface should not have '{name}' method"

    def test_things_persist_after_alter(self, place: PlaceInterface, place_path: Path):
        """Altering changes content but the file still exists."""
        place.create("a stone", "Grey.")
        place.alter("a stone", description="Now warm.")
        assert (place_path / "a stone.md").exists()

    def test_renamed_things_old_file_gone_new_exists(self, place: PlaceInterface, place_path: Path):
        """Renaming replaces the file — the old name is gone, new name exists."""
        place.create("a stone", "Grey.")
        place.alter("a stone", name="a pebble")
        assert not (place_path / "a stone.md").exists()
        assert (place_path / "a pebble.md").exists()
