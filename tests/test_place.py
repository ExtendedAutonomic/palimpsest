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

    def test_venture_into_own_space_reconnects(self, place: PlaceInterface):
        """Venturing into a space you created gives the 'been here before' message."""
        place.venture("the garden", "A quiet place.")
        place.go("here")
        place.venture("the library", "Shelves of dust.")
        result = place.venture("the garden", "Something different.")
        assert "already exists" in result
        assert "You have been here before" in result
        assert place.current_location == "the garden"

    def test_venture_into_others_space_signals_otherness(self, place: PlaceInterface, place_path: Path):
        """Venturing into a space created by another agent gives the 'did not create' message."""
        # Simulate another agent having created a space
        from orchestrator.place.notes import build_space_note
        fm = {
            "type": "space",
            "created_by": "other-agent",
            "created_session": 1,
            "updated_by": "other-agent",
            "updated_session": 1,
        }
        (place_path / "the quiet room.md").write_text(
            build_space_note("A room you did not make.", [], [], fm),
            encoding="utf-8",
        )
        result = place.venture("the quiet room", "Something.")
        assert "already exists" in result
        assert "You did not create this place" in result
        assert place.current_location == "the quiet room"

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
        assert "connected to" in result
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


class TestTakeAndDrop:
    """Hidden tools unlocked when an agent tries to examine something left behind."""

    def _setup_two_spaces_with_thing(self, place: PlaceInterface):
        """Create a thing in here, then venture to a new space."""
        place.create("a stone", "A smooth dark stone.")
        place.venture("the shore", "A grey shore.")
        return place

    def test_examine_thing_in_other_space_unlocks_take(self, place: PlaceInterface):
        self._setup_two_spaces_with_thing(place)
        result = place.examine("a stone")
        assert "left it behind" in result.lower()
        assert "take" in place._unlocked_tools
        assert "drop" in place._unlocked_tools

    def test_examine_nonexistent_thing_does_not_unlock(self, place: PlaceInterface):
        self._setup_two_spaces_with_thing(place)
        result = place.examine("a fish")
        assert "nothing called" in result.lower()
        assert len(place._unlocked_tools) == 0

    def test_examine_space_in_other_location_does_not_unlock(self, place: PlaceInterface):
        """Only things trigger the unlock, not spaces."""
        self._setup_two_spaces_with_thing(place)
        # "here" exists but is a space, not a thing
        result = place.examine("here")
        assert "take" not in place._unlocked_tools

    def test_take_thing_from_current_space(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        result = place.take("a stone")
        assert "with you" in result.lower()
        assert "a stone" in place._carrying
        # Thing should be removed from space
        note = place._read_note("here")
        assert "a stone" not in note.things

    def test_take_thing_not_here(self, place: PlaceInterface):
        result = place.take("a stone")
        assert "nothing" in result.lower()

    def test_take_already_carrying(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        result = place.take("a stone")
        assert "already carrying" in result.lower()

    def test_drop_thing(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        place.venture("the shore", "A grey shore.")
        result = place.drop("a stone")
        assert "here now" in result.lower()
        assert "a stone" not in place._carrying
        # Thing should be linked in the new space
        note = place._read_note("the shore")
        assert "a stone" in note.things

    def test_drop_not_carrying(self, place: PlaceInterface):
        result = place.drop("a stone")
        assert "not carrying" in result.lower()

    def test_perceive_shows_carried_things(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        result = place.perceive()
        assert "carrying" in result.lower()
        assert "a stone" in result

    def test_perceive_without_carried_things(self, place: PlaceInterface):
        result = place.perceive()
        assert "carrying" not in result.lower()

    def test_examine_carried_thing_in_different_space(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        place.venture("the shore", "A grey shore.")
        result = place.examine("a stone")
        assert "smooth dark stone" in result.lower()

    def test_take_links_to_inventory(self, place: PlaceInterface, place_path: Path):
        """When taken, thing moves from space to Inventory node."""
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        # Note file should still exist
        assert (place_path / "a stone.md").exists()
        # Not linked from original space
        here_note = place._read_note("here")
        assert "a stone" not in here_note.things
        # Linked from Inventory
        inv_note = place._read_note("Inventory")
        assert inv_note is not None
        assert "a stone" in inv_note.things

    def test_drop_moves_from_inventory_to_space(self, place: PlaceInterface):
        """When dropped, thing moves from Inventory to new space."""
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        place.venture("the shore", "A grey shore.")
        place.drop("a stone")
        shore_note = place._read_note("the shore")
        assert "a stone" in shore_note.things
        here_note = place._read_note("here")
        assert "a stone" not in here_note.things
        # No longer in Inventory
        inv_note = place._read_note("Inventory")
        assert "a stone" not in inv_note.things

    def test_full_journey_take_carry_drop(self, place: PlaceInterface):
        """End-to-end: create, take, travel, examine while carrying, drop elsewhere."""
        place.create("the compass", "A black glass compass.")
        place.take("the compass")
        place.venture("the island", "A dark island.")
        # Can examine while carrying
        result = place.examine("the compass")
        assert "black glass" in result.lower()
        # Perceive shows it
        result = place.perceive()
        assert "the compass" in result
        assert "carrying" in result.lower()
        # Drop it here
        place.drop("the compass")
        # Now it's in the island
        island = place._read_note("the island")
        assert "the compass" in island.things
        # And not carried
        assert "the compass" not in place._carrying

    def test_unlock_persists_across_sessions(self, place_path: Path):
        """Unlocked tools survive PlaceInterface recreation (new session)."""
        place1 = PlaceInterface(place_path, agent_name="test-agent", session_number=1)
        place1.create("a stone", "A smooth dark stone.")
        place1.venture("the shore", "A grey shore.")
        place1.examine("a stone")  # triggers unlock
        assert "take" in place1.permanently_unlocked_tools

        # New session — fresh PlaceInterface
        place2 = PlaceInterface(place_path, agent_name="test-agent", session_number=2)
        assert "take" in place2.permanently_unlocked_tools
        assert "drop" in place2.permanently_unlocked_tools
