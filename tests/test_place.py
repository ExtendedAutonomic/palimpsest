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
from orchestrator.place.notes import parse_note, build_space_note


class TestFoundingSpace:
    """The place begins with a single empty space called 'here'."""

    def test_starts_at_here(self, place: PlaceInterface):
        assert place.current_location == "here"

    def test_perceive_empty_here(self, place: PlaceInterface):
        _, result = place.perceive()
        assert result == "here"

    def test_here_md_exists(self, place_path: Path):
        assert (place_path / "here.md").exists()

    def test_here_is_a_space(self, place_path: Path):
        note = parse_note((place_path / "here.md").read_text(encoding="utf-8"))
        assert note.note_type == "space"


class TestVenture:
    """Venturing creates new spaces and links them bidirectionally."""

    def test_venture_creates_space_and_moves(self, place: PlaceInterface):
        _, result = place.venture("the garden", "A quiet place with tall grass.")
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
        """Venturing into a space you created gives the 'already exists' message."""
        place.venture("the garden", "A quiet place.")
        place.go("here")
        place.venture("the library", "Shelves of dust.")
        _, result = place.venture("the garden", "Something different.")
        assert "already exists" in result
        assert "You are now at the garden" in result
        assert place.current_location == "the garden"

    def test_venture_into_others_space_same_message(self, place: PlaceInterface, place_path: Path):
        """Venturing into a space created by another agent gives the same message."""
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
        _, result = place.venture("the quiet room", "Something.")
        assert "already exists" in result
        assert "You are now at the quiet room" in result
        assert place.current_location == "the quiet room"

    def test_venture_into_existing_thing_fails(self, place: PlaceInterface):
        """Can't create a space with the same name as an existing thing."""
        place.create("a stone", "Grey and smooth.")
        _, result = place.venture("a stone", "A rocky chamber.")
        assert "already exists" in result
        assert place.current_location == "here"  # Didn't move


class TestCreate:
    """Creating makes things that persist in the current space."""

    def test_create_thing(self, place: PlaceInterface):
        _, result = place.create("a stone", "Grey and smooth, cold to the touch.")
        assert "Grey and smooth" in result

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
        _, result = place.create("a stone", "A different stone.")
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
        _, result = place.examine("a stone")
        assert "Grey and smooth" in result

    def test_examine_current_space(self, place: PlaceInterface):
        place.venture("the garden", "Tall grass and wildflowers.")
        _, result = place.examine("the garden")
        assert "Tall grass" in result

    def test_examine_empty_space(self, place: PlaceInterface):
        _, result = place.examine("here")
        assert "no particular quality" in result.lower()

    def test_examine_nonexistent(self, place: PlaceInterface):
        _, result = place.examine("nothing")
        assert "nothing called" in result.lower()

    def test_examine_connected_space_not_here(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        _, result = place.examine("the garden")
        assert "not in that space" in result.lower()

    def test_examine_thing_in_other_space_not_visible(self, place: PlaceInterface):
        """Things in other spaces aren't examinable from here — no hint given."""
        place.venture("the garden", "A quiet place.")
        place.create("a flower", "Red.")
        place.go("here")
        _, result = place.examine("a flower")
        assert "nothing called" in result.lower()


class TestGo:
    """Movement between connected spaces."""

    def test_go_to_connected_space(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        _, result = place.go("the garden")
        assert "the garden" in result
        assert "A quiet place" in result
        assert place.current_location == "the garden"

    def test_go_to_unconnected_space_fails(self, place: PlaceInterface):
        _, result = place.go("nowhere")
        assert "no space" in result.lower()
        assert place.current_location == "here"

    def test_go_to_thing_fails(self, place: PlaceInterface):
        """Trying to go to a thing gives a specific error, not the generic 'no space' message."""
        place.create("a stone", "Grey and smooth.")
        _, result = place.go("a stone")
        assert "is not a space" in result.lower()
        assert "no space called" not in result.lower()
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
        _, result = place.alter("a stone", description="Now cracked and warm.")
        assert "Now cracked and warm" in result

    def test_alter_thing_content_changes(self, place: PlaceInterface):
        place.create("a stone", "Grey and smooth.")
        place.alter("a stone", description="Now cracked and warm.")
        _, result = place.examine("a stone")
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
        _, result = place.alter("the garden", description="Now overgrown and wild.")
        assert "Now overgrown and wild" in result

    def test_alter_current_space_name(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.alter("the garden", name="the wilderness")
        assert place.current_location == "the wilderness"

    def test_alter_nonexistent_fails(self, place: PlaceInterface):
        _, result = place.alter("nothing", description="Something.")
        assert "nothing called" in result.lower()

    def test_alter_with_no_changes_fails(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        _, result = place.alter("a stone")
        assert "must specify" in result.lower()

    def test_alter_to_existing_name_fails(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        place.create("a pebble", "Small.")
        _, result = place.alter("a stone", name="a pebble")
        assert "already exists" in result


class TestPerceive:
    """Perceiving reveals the current space's contents."""

    def test_perceive_shows_spaces(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        _, result = place.perceive()
        assert "connected to" in result
        assert "the garden" in result

    def test_perceive_shows_things(self, place: PlaceInterface):
        place.create("a stone", "Grey.")
        _, result = place.perceive()
        assert "a stone" in result

    def test_perceive_shows_space_name(self, place: PlaceInterface):
        place.venture("the garden", "Tall grass and wildflowers.")
        _, result = place.perceive()
        assert result.startswith("the garden")

    def test_perceive_shows_description(self, place: PlaceInterface):
        place.venture("the garden", "Tall grass and wildflowers.")
        _, result = place.perceive()
        assert "Tall grass" in result

    def test_perceive_shows_both_spaces_and_things(self, place: PlaceInterface):
        place.venture("the garden", "A quiet place.")
        place.go("here")
        place.create("a stone", "Grey.")
        _, result = place.perceive()
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
        _, perceive_result = place.perceive()
        assert "a seed" not in perceive_result

        # But the garden should be
        assert "the garden" in perceive_result

        # Go back and the seed is there
        place.go("the garden")
        _, result = place.perceive()
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
        _, result = place.examine("a message")
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
    """Taking and dropping things between spaces."""

    def _setup_two_spaces_with_thing(self, place: PlaceInterface):
        """Create a thing in here, then venture to a new space."""
        place.create("a stone", "A smooth dark stone.")
        place.venture("the shore", "A grey shore.")
        return place

    def test_examine_thing_in_other_space_not_visible(self, place: PlaceInterface):
        self._setup_two_spaces_with_thing(place)
        _, result = place.examine("a stone")
        assert "nothing called" in result.lower()

    def test_examine_nonexistent_thing(self, place: PlaceInterface):
        self._setup_two_spaces_with_thing(place)
        _, result = place.examine("a fish")
        assert "nothing called" in result.lower()

    def test_take_thing_from_current_space(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        _, result = place.take("a stone")
        assert "with you" in result.lower()
        assert "a stone" in place._carrying
        # Thing should be removed from space
        note = place._read_note("here")
        assert "a stone" not in note.things

    def test_take_thing_not_here(self, place: PlaceInterface):
        _, result = place.take("a stone")
        assert "nothing" in result.lower()

    def test_take_already_carrying(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        _, result = place.take("a stone")
        assert "already have" in result.lower()

    def test_drop_thing(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        place.venture("the shore", "A grey shore.")
        _, result = place.drop("a stone")
        assert "the shore" in result.lower()
        assert "a stone" not in place._carrying
        # Thing should be linked in the new space
        note = place._read_note("the shore")
        assert "a stone" in note.things

    def test_drop_not_carrying(self, place: PlaceInterface):
        _, result = place.drop("a stone")
        assert "do not have" in result.lower()

    def test_perceive_shows_carried_things(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        _, result = place.perceive()
        assert "carrying" in result.lower()
        assert "a stone" in result

    def test_perceive_without_carried_things(self, place: PlaceInterface):
        _, result = place.perceive()
        assert "carrying" not in result.lower()

    def test_examine_carried_thing_in_different_space(self, place: PlaceInterface):
        place.create("a stone", "A smooth dark stone.")
        place.take("a stone")
        place.venture("the shore", "A grey shore.")
        _, result = place.examine("a stone")
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
        inv_note = place._read_note("inventory_test-agent")
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
        inv_note = place._read_note("inventory_test-agent")
        assert "a stone" not in inv_note.things

    def test_full_journey_take_carry_drop(self, place: PlaceInterface):
        """End-to-end: create, take, travel, examine while carrying, drop elsewhere."""
        place.create("the compass", "A black glass compass.")
        place.take("the compass")
        place.venture("the island", "A dark island.")
        # Can examine while carrying
        _, result = place.examine("the compass")
        assert "black glass" in result.lower()
        # Perceive shows it
        _, result = place.perceive()
        assert "the compass" in result
        assert "carrying" in result.lower()
        # Drop it here
        place.drop("the compass")
        # Now it's in the island
        island = place._read_note("the island")
        assert "the compass" in island.things
        # And not carried
        assert "the compass" not in place._carrying


class TestDisplayNames:
    """Display names decouple the agent's experience from filenames.

    When a note has a `name` field in frontmatter, the agent sees that
    name instead of the filename. This allows multiple notes to share
    the same display name (e.g. three agents each having a space called
    'here') while remaining distinct files on disk.
    """

    @pytest.fixture
    def multi_place(self, tmp_path: Path) -> tuple[PlaceInterface, Path]:
        """A place with two agents' territories sharing display names.

        Mimics the unified Place: here.md (agent A), here_b.md (agent B,
        display name 'here'), and B's cave system.
        """
        p = tmp_path / "place"
        p.mkdir()

        # Agent A's founding space — filename IS the display name
        (p / "here.md").write_text(
            build_space_note(
                description="Cool grass, indigo sky, a small fire.",
                spaces=[], things=["a stone"],
                frontmatter={
                    "type": "space", "created_by": "place",
                    "created_session": 0, "updated_by": "claude",
                    "updated_session": 3, "occupant": "claude",
                },
            ), encoding="utf-8",
        )
        (p / "a stone.md").write_text(
            "---\ntype: thing\ncreated_by: claude\ncreated_session: 1\n"
            "updated_by: claude\nupdated_session: 1\n---\n"
            "A smooth stone.\n", encoding="utf-8",
        )

        # Agent B's founding space — filename differs from display name
        (p / "here_b.md").write_text(
            build_space_note(
                description="",
                spaces=["the descent"], things=["the cave"],
                frontmatter={
                    "type": "space", "name": "here",
                    "created_by": "place", "created_session": 0,
                    "updated_by": "claude_b", "updated_session": 1,
                },
            ), encoding="utf-8",
        )
        (p / "the descent.md").write_text(
            build_space_note(
                description="A narrow passage descending into darkness.",
                spaces=["here_b", "the green deep"], things=["the marks"],
                frontmatter={
                    "type": "space", "created_by": "claude_b",
                    "created_session": 1, "updated_by": "claude_b",
                    "updated_session": 4,
                },
            ), encoding="utf-8",
        )
        (p / "the green deep.md").write_text(
            build_space_note(
                description="A garden growing in the dark.",
                spaces=["the descent"], things=[],
                frontmatter={
                    "type": "space", "created_by": "claude_b",
                    "created_session": 2, "updated_by": "claude_b",
                    "updated_session": 4,
                },
            ), encoding="utf-8",
        )
        (p / "the cave.md").write_text(
            "---\ntype: thing\ncreated_by: claude_b\ncreated_session: 1\n"
            "updated_by: claude_b\nupdated_session: 1\n---\n"
            "Wet stone and stalactites.\n", encoding="utf-8",
        )
        (p / "the marks.md").write_text(
            "---\ntype: thing\ncreated_by: claude_b\ncreated_session: 2\n"
            "updated_by: claude_b\nupdated_session: 2\n---\n"
            "Ancient spirals carved into stone.\n", encoding="utf-8",
        )

        # Agent C's space — display name 'here', different filename
        (p / "here_c.md").write_text(
            build_space_note(
                description="",
                spaces=[], things=["a small stone", "a second stone_c"],
                frontmatter={
                    "type": "space", "name": "here",
                    "created_by": "place", "created_session": 0,
                    "updated_by": "claude_c", "updated_session": 2,
                    "occupant": "claude_c",
                },
            ), encoding="utf-8",
        )
        (p / "a small stone.md").write_text(
            "---\ntype: thing\ncreated_by: claude_c\ncreated_session: 1\n"
            "updated_by: claude_c\nupdated_session: 1\n---\n"
            "A warm stone.\n", encoding="utf-8",
        )
        (p / "a second stone_c.md").write_text(
            "---\ntype: thing\nname: a second stone\n"
            "created_by: claude_c\ncreated_session: 2\n"
            "updated_by: claude_c\nupdated_session: 2\n---\n"
            "A cool stone.\n", encoding="utf-8",
        )

        place = PlaceInterface(p, agent_name="claude_b", session_number=6)
        place.current_location = "the descent"
        return place, p

    # --- display_name ---

    def test_display_name_with_override(self, multi_place):
        place, _ = multi_place
        assert place.display_name("here_b") == "here"

    def test_display_name_without_override(self, multi_place):
        place, _ = multi_place
        assert place.display_name("the descent") == "the descent"

    def test_display_name_thing_override(self, multi_place):
        place, _ = multi_place
        assert place.display_name("a second stone_c") == "a second stone"

    # --- perceive ---

    def test_perceive_shows_display_names(self, multi_place):
        """Perceive at the descent should show 'here' not 'here_b'."""
        place, _ = multi_place
        _, result = place.perceive()
        assert "here" in result
        assert "here_b" not in result

    def test_perceive_c_shows_display_names(self, multi_place):
        """Agent C perceiving should see 'a second stone' not 'a second stone_c'."""
        place, p = multi_place
        c = PlaceInterface(p, agent_name="claude_c", session_number=11)
        c.current_location = "here_c"
        _, result = c.perceive()
        assert "a second stone" in result
        assert "a second stone_c" not in result

    # --- go ---

    def test_go_with_display_name(self, multi_place):
        """Agent B says 'go here' and lands at here_b, not here.md."""
        place, _ = multi_place
        success, result = place.go("here")
        assert success
        assert place.current_location == "here_b"

    def test_go_preserves_display_name_in_response(self, multi_place):
        place, _ = multi_place
        _, result = place.go("here")
        assert "here" in result
        assert "here_b" not in result

    def test_go_without_display_name(self, multi_place):
        place, _ = multi_place
        success, _ = place.go("the green deep")
        assert success
        assert place.current_location == "the green deep"

    # --- examine ---

    def test_examine_thing_in_space(self, multi_place):
        place, _ = multi_place
        success, result = place.examine("the marks")
        assert success
        assert "spirals" in result.lower()

    def test_examine_current_space_by_display_name(self, multi_place):
        """Agent B at the descent can examine it by display name."""
        place, _ = multi_place
        success, result = place.examine("the descent")
        assert success
        assert "passage" in result.lower()

    # --- venture collision with display names ---

    def test_venture_collision_finds_oldest(self, multi_place):
        """If agent B ventures to 'here', it should collide with the oldest
        space named 'here' — which is here.md (A's space, session 0, oldest)."""
        place, _ = multi_place
        # Move to green deep first so descent isn't directly connected to 'here'
        place.go("the green deep")
        success, result = place.venture("here", "A new place.")
        assert success
        assert "already exists" in result
        # Should land at here.md (A's, oldest) not here_b or here_c
        assert place.current_location == "here"

    # --- create collision with display names ---

    def test_create_blocked_by_display_name(self, multi_place):
        """Cannot create 'a second stone' because a second stone_c has that display name."""
        place, _ = multi_place
        success, result = place.create("a second stone", "Another stone.")
        assert not success
        assert "already exists" in result

    # --- filenames dict on tool calls ---

    def test_go_populates_filenames(self, multi_place):
        """ToolCall.filenames should map 'where' to the resolved filename."""
        place, _ = multi_place
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(tool=ToolName.GO, arguments={"where": "here"})
        place.execute_tool(tc)
        assert tc.filenames.get("where") == "here_b"

    def test_examine_populates_filenames(self, multi_place):
        place, _ = multi_place
        from orchestrator.place.tools import ToolCall, ToolName
        tc = ToolCall(tool=ToolName.EXAMINE, arguments={"what": "the marks"})
        place.execute_tool(tc)
        assert tc.filenames.get("what") == "the marks"


