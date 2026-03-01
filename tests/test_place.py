"""
Integration tests for the place — the spatial environment agents inhabit.

Tests the full journey: perceive → venture → create → examine → go → alter,
all operating on real files in a temporary directory. These tests verify
the place works as a coherent spatial system, not just that individual
methods return strings.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.place import PlaceInterface
from orchestrator.place.notes import parse_note


class TestFoundingSpace:
    """The place begins with a single empty space called 'here'."""

    def test_starts_at_here(self, place: PlaceInterface):
        assert place.current_location == "here"

    def test_perceive_empty_here(self, place: PlaceInterface):
        result = place.perceive()
        assert "empty" in result.lower()

    def test_here_md_exists(self, place_path: Path):
        assert (place_path / "here.md").exists()

    def test_here_is_a_space(self, place_path: Path):
        note = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert note.note_type == "space"


class TestVenture:
    """Venturing creates new spaces and links them bidirectionally."""

    def test_venture_creates_space_and_moves(self, place: PlaceInterface):
        result = place.venture("the garden", "A quiet place with tall grass.")
        assert "the garden" in result
        assert place.current_location == "the garden"

    def test_venture_creates_file(self, place: PlaceInterface, place_path: Path):
        place.venture("the garden", "A quiet place with tall grass.")
        assert (place_path / "the garden.md").exists()

    def test_venture_links_back_to_origin(self, place: PlaceInterface, place_path: Path):
        place.venture("the garden", "A quiet place.")
        note = parse_note((place_path / "the garden.md").read_text(encoding="utf-8"))
        assert "here" in note.spaces

    def test_venture_links_origin_to_new(self, place: PlaceInterface, place_path: Path):
        place.venture("the garden", "A quiet place.")
        note = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert "the garden" in note.spaces

    def test_venture_sets_frontmatter(self, place: PlaceInterface, place_path: Path):
        place.venture("the garden", "A quiet place.")
        note = parse_note((place_path / "the garden.md").read_text(encoding="utf-8"))
        assert note.frontmatter["type"] == "space"
        assert note.frontmatter["created_by"] == "test-agent"
        assert note.frontmatter["created_session"] == 1

    def test_venture_into_existing_space_connects(self, place: PlaceInterface):
        """If a space already exists, venture connects to it instead of failing."""
        place.venture("the garden", "A quiet place.")
        place.go("here")
        # Now venture to a second space, then back to the garden from here
        place.venture("the library", "Shelves of dust.")
        result = place.venture("the garden", "Something different.")
        assert "already exists" in result
        assert place.current_location == "the garden"

    def test_venture_into_existing_thing_fails(self, place: PlaceInterface):
        """Can't create a space with the same name as an existing thing."""
        place.create("a stone", "Grey and smooth.")
        result = place.venture("a stone", "A rocky chamber.")
        assert "not a space" in result
        assert place.current_location == "here"  # Didn't move


class TestCreate:
    """Creating makes things that persist in the current space."""

    def test_create_thing(self, place: PlaceInterface):
        result = place.create("a stone", "Grey and smooth, cold to the touch.")
        assert "a stone" in result
        assert "remain" in result

    def test_create_makes_file(self, place: PlaceInterface, place_path: Path):
        place.create("a stone", "Grey and smooth.")
        assert (place_path / "a stone.md").exists()

    def test_create_links_to_current_space(self, place: PlaceInterface, place_path: Path):
        place.create("a stone", "Grey and smooth.")
        note = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert "a stone" in note.things

    def test_create_thing_has_correct_type(self, place: PlaceInterface, place_path: Path):
        place.create("a stone", "Grey and smooth.")
        note = parse_note((place_path / "a stone.md").read_text(encoding="utf-8"))
        assert note.note_type == "thing"

    def test_create_duplicate_fails(self, place: PlaceInterface):
        place.create("a stone", "Grey and smooth.")
        result = place.create("a stone", "A different stone.")
        assert "already exists" in result

    def test_create_in_ventured_space(self, place: PlaceInterface, place_path: Path):
        """Things created after venturing appear in the new space, not the old one."""
        place.venture("the garden", "A quiet place.")
        place.create("a flower", "Red petals, still wet.")

        garden = parse_note((place_path / "the garden.md").read_text(encoding="utf-8"))
        assert "a flower" in garden.things

        here = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert "a flower" not in here.things


class TestExamine:
    """Examining reveals the content of things and spaces."""

    def test_examine_thing(self, place: PlaceInterface):
        place.create("a stone", "Grey and smooth, cold to the touch.")
        result = place.examine("a stone")
        assert "Grey and smooth" in result

    def test_examine_current_space(self, place: PlaceInterface):
        place.venture("the garden", "Tall grass and wildflowers.")
        result = place.examine("the garden")
        assert "Tall grass" in result

    def test_examine_empty_space(self, place: PlaceInterface):
        result = place.examine("here")
        assert "no particular quality" in result.lower()

    def test_examine_nonexistent(self, place: PlaceInterface):
        result = place.examine("nothing")
        assert "nothing called" in result.lower()

    def test_examine_connected_space_suggests_go(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        result = place.examine("the garden")
        assert "go there" in result.lower()

    def test_examine_thing_in_other_space_not_visible(self, place: PlaceInterface):
        """Things in other spaces aren't visible from the current space."""
        place.venture("the garden", "A quiet place.")
        place.create("a flower", "Red.")
        place.go("here")
        result = place.examine("a flower")
        assert "nothing called" in result.lower()


class TestGo:
    """Movement between connected spaces."""

    def test_go_to_connected_space(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        result = place.go("the garden")
        assert "the garden" in result
        assert place.current_location == "the garden"

    def test_go_to_unconnected_space_fails(self, place: PlaceInterface):
        result = place.go("nowhere")
        assert "no space" in result.lower()
        assert place.current_location == "here"

    def test_go_back_and_forth(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        assert place.current_location == "the garden"
        place.go("here")
        assert place.current_location == "here"
        place.go("the garden")
        assert place.current_location == "the garden"


class TestAlter:
    """Altering changes things and spaces that exist."""

    def test_alter_thing_description(self, place: PlaceInterface):
        place.create("a stone", "Grey and smooth.")
        result = place.alter("a stone", description="Now cracked and warm.")
        assert "different" in result

    def test_alter_thing_content_changes(self, place: PlaceInterface):
        place.create("a stone", "Grey and smooth.")
        place.alter("a stone", description="Now cracked and warm.")
        result = place.examine("a stone")
        assert "cracked and warm" in result
        assert "Grey" not in result

    def test_alter_thing_name(self, place: PlaceInterface, place_path: Path):
        place.create("a stone", "Grey and smooth.")
        place.alter("a stone", name="a pebble")
        assert not (place_path / "a stone.md").exists()
        assert (place_path / "a pebble.md").exists()

    def test_alter_thing_name_updates_links(self, place: PlaceInterface, place_path: Path):
        place.create("a stone", "Grey and smooth.")
        place.alter("a stone", name="a pebble")
        here = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert "a pebble" in here.things
        assert "a stone" not in here.things

    def test_alter_current_space_description(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        result = place.alter("the garden", description="Now overgrown and wild.")
        assert "different" in result

    def test_alter_current_space_name(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.alter("the garden", name="the wilderness")
        assert place.current_location == "the wilderness"

    def test_alter_nonexistent_fails(self, place: PlaceInterface):
        result = place.alter("nothing", description="Something.")
        assert "nothing called" in result.lower()

    def test_alter_with_no_changes_fails(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        result = place.alter("a stone")
        assert "must change" in result.lower()

    def test_alter_to_existing_name_fails(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        place.create("a pebble", "Small.")
        result = place.alter("a stone", name="a pebble")
        assert "already exists" in result


class TestPerceive:
    """Perceiving reveals the current space's contents."""

    def test_perceive_shows_spaces(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        result = place.perceive()
        assert "the garden" in result

    def test_perceive_shows_things(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        result = place.perceive()
        assert "a stone" in result

    def test_perceive_shows_description(self, place: PlaceInterface):
        place.venture("the garden", "Tall grass and wildflowers.")
        result = place.perceive()
        assert "Tall grass" in result

    def test_perceive_shows_both_spaces_and_things(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        place.create("a stone", "Grey.")
        result = place.perceive()
        assert "the garden" in result
        assert "a stone" in result


class TestMultiStepJourney:
    """
    End-to-end journeys through the place — the kind of thing
    an agent would actually do across a session.
    """

    def test_explore_create_return_examine(self, place: PlaceInterface):
        """Venture out, create something, return home, verify it's not visible."""
        place.venture("the garden", "Wildflowers and silence.")
        place.create("a seed", "Planted in dark soil.")
        place.go("here")

        # From here, the seed shouldn't be visible
        perceive_result = place.perceive()
        assert "a seed" not in perceive_result

        # But the garden should be
        assert "the garden" in perceive_result

        # Go back and the seed is there
        place.go("the garden")
        result = place.perceive()
        assert "a seed" in result

    def test_build_a_topology(self, place: PlaceInterface, place_path: Path):
        """Create a multi-room structure and navigate it."""
        # here → garden → greenhouse
        place.venture("the garden", "Open air.")
        place.venture("the greenhouse", "Glass walls, warm.")

        # Navigate back to here
        place.go("the garden")
        place.go("here")

        # Verify topology: here connects to garden, garden connects to both
        here = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert "the garden" in here.spaces
        assert "the greenhouse" not in here.spaces  # Not directly connected

        garden = parse_note((place_path / "the garden.md").read_text(encoding="utf-8"))
        assert "here" in garden.spaces
        assert "the greenhouse" in garden.spaces

    def test_alter_then_examine_shows_new_content(self, place: PlaceInterface):
        """Create, alter, then verify the change persists."""
        place.create("a message", "Hello.")
        place.alter("a message", description="Goodbye.")
        result = place.examine("a message")
        assert "Goodbye" in result
        assert "Hello" not in result


class TestExecuteTool:
    """Test the execute_tool dispatch method."""

    def test_execute_perceive(self, place: PlaceInterface):
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(tool=ToolName.PERCEIVE, arguments={})
        result = place.execute_tool(tc)
        assert isinstance(result, str)
        assert tc.result == result

    def test_execute_venture(self, place: PlaceInterface):
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(
            tool=ToolName.VENTURE,
            arguments={"name": "the garden", "description": "Flowers."},
        )
        result = place.execute_tool(tc)
        assert "the garden" in result
        assert place.current_location == "the garden"

    def test_execute_unknown_tool(self, place: PlaceInterface):
        """Unknown tools return a gentle failure, not an exception."""
        from orchestrator.place.tools import ToolCall
        tc = ToolCall(tool="fly", arguments={})
        result = place.execute_tool(tc)
        assert "do not know" in result.lower()

    def test_execute_records_error_on_bad_name(self, place: PlaceInterface):
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(
            tool=ToolName.VENTURE,
            arguments={"name": "../escape", "description": "Bad."},
        )
        result = place.execute_tool(tc)
        assert "prevented" in result.lower() or "not possible" in result.lower()
        assert tc.error is not None
