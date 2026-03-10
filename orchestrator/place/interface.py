"""
PlaceInterface for Palimpsest.

The place as experienced by an agent — linked notes in a flat directory.
Every space and thing is a markdown note. Spaces contain wiki links
to connected spaces and things. The agent navigates by following links.

All responses are written in the language of the place, never in
filesystem or markdown terminology.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .notes import ParsedNote, parse_note, build_space_note, build_thing_note
from .tools import ToolCall, ToolName

logger = logging.getLogger(__name__)


def _get_creation_time_ns(path: Path) -> int | None:
    """Get a file's creation time in nanoseconds, or None if it doesn't exist."""
    if not path.exists():
        return None
    return path.stat().st_ctime_ns


def _set_creation_time(path: Path, creation_time_ns: int) -> None:
    """Restore a file's creation time on Windows. No-op on other platforms.

    Obsidian's graph animation uses filesystem creation times to order
    note appearance. Without this, any file rewrite (alter, link update,
    occupant change) would reset the creation time and break the timeline.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        # Convert nanoseconds to Windows FILETIME (100ns intervals since 1601-01-01)
        EPOCH_DIFF_100NS = 116444736000000000
        filetime_int = (creation_time_ns // 100) + EPOCH_DIFF_100NS

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            str(path),
            256,   # FILE_WRITE_ATTRIBUTES
            7,     # FILE_SHARE_READ | WRITE | DELETE
            None,
            3,     # OPEN_EXISTING
            128,   # FILE_ATTRIBUTE_NORMAL
            None,
        )
        if handle == -1:
            return
        try:
            ft = wintypes.FILETIME(
                filetime_int & 0xFFFFFFFF,
                (filetime_int >> 32) & 0xFFFFFFFF,
            )
            kernel32.SetFileTime(handle, ctypes.byref(ft), None, None)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass  # Best-effort


class PlaceInterface:
    """
    The place as experienced by an agent — linked notes in a flat directory.
    """

    def __init__(self, place_path: Path, agent_name: str = "", session_number: int = 0):
        self.place_path = place_path.resolve()
        self._current_location: str | None = None
        self._agent_name = agent_name
        self._session_number = session_number
        self._carrying: list[str] = []  # Things the agent is carrying
        self._unlocked_tools: set[str] = set()  # Newly unlocked this turn (consumed by session loop)
        self._load_unlocked_tools()

    @property
    def current_location(self) -> str:
        return self._current_location

    @current_location.setter
    def current_location(self, value: str) -> None:
        if value != self._current_location:
            if self._current_location is not None:
                self._clear_occupant(self._current_location)
            self._current_location = value
            self._set_occupant(value)
        else:
            self._current_location = value

    def _set_occupant(self, location: str) -> None:
        """Mark a space as occupied by this agent in its frontmatter."""
        note = self._read_note(location)
        if not note or note.note_type != "space":
            return
        fm = dict(note.frontmatter)
        fm["occupant"] = self._agent_name
        self._write_note(location, build_space_note(
            note.description, note.spaces, note.things, fm
        ))

    def _clear_occupant(self, location: str) -> None:
        """Remove the occupant property from a space."""
        note = self._read_note(location)
        if not note or note.note_type != "space":
            return
        fm = dict(note.frontmatter)
        fm.pop("occupant", None)
        self._write_note(location, build_space_note(
            note.description, note.spaces, note.things, fm
        ))

    def _unlocked_tools_path(self) -> Path:
        return self.place_path / ".unlocked_tools.json"

    def _load_unlocked_tools(self) -> None:
        """Load previously unlocked tools from disk."""
        import json
        path = self._unlocked_tools_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._permanently_unlocked: set[str] = set(data.get("tools", []))
        else:
            self._permanently_unlocked: set[str] = set()

    def _save_unlocked_tools(self) -> None:
        """Persist unlocked tools to disk."""
        import json
        path = self._unlocked_tools_path()
        path.write_text(
            json.dumps({"tools": sorted(self._permanently_unlocked)}),
            encoding="utf-8",
        )

    def unlock_tool(self, tool_name: str) -> None:
        """Unlock a hidden tool permanently."""
        if tool_name not in self._permanently_unlocked:
            self._permanently_unlocked.add(tool_name)
            self._unlocked_tools.add(tool_name)  # Signal to session loop
            self._save_unlocked_tools()

    @property
    def permanently_unlocked_tools(self) -> set[str]:
        return self._permanently_unlocked

    @staticmethod
    def _sanitise_name(name: str, empty_message: str = "You must give it a name.") -> str:
        """Reject names that could break the place."""
        forbidden = ["..", "/", "\\", "\x00", "[[", "]]", "|", "#"]
        for pattern in forbidden:
            if pattern in name:
                raise ValueError("That name is not possible here.")
        if name.startswith("."):
            raise ValueError("That name is not possible here.")
        if not name.strip():
            raise ValueError(empty_message)
        return name.strip()

    def _note_path(self, name: str) -> Path:
        """Get the filesystem path for a note.

        Resolves the path and verifies it stays within the place directory.
        This is a defence-in-depth check — _sanitise_name rejects obvious
        traversal patterns, but this catches anything that slips through.
        """
        path = (self.place_path / f"{name}.md").resolve()
        if not path.is_relative_to(self.place_path):
            raise ValueError("That name is not possible here.")
        return path

    def _note_exists(self, name: str) -> bool:
        """Check if a note exists."""
        return self._note_path(name).exists()

    def _read_note(self, name: str) -> ParsedNote | None:
        """Read and parse a note."""
        path = self._note_path(name)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        return parse_note(text)

    def _write_note(self, name: str, content: str, preserve_ctime: bool = True) -> None:
        """Write a note to disk, preserving creation time for existing files."""
        path = self._note_path(name)
        original_ctime = _get_creation_time_ns(path) if preserve_ctime else None
        path.write_text(content, encoding="utf-8")
        if original_ctime is not None:
            _set_creation_time(path, original_ctime)

    def _make_frontmatter(self, note_type: str) -> dict[str, Any]:
        """Create frontmatter for a new note."""
        return {
            "type": note_type,
            "created_by": self._agent_name,
            "created_session": self._session_number,
            "updated_by": self._agent_name,
            "updated_session": self._session_number,
        }

    def _update_frontmatter(self, existing: dict[str, Any]) -> dict[str, Any]:
        """Update frontmatter for an edited note."""
        updated = dict(existing)
        updated["updated_by"] = self._agent_name
        updated["updated_session"] = self._session_number
        return updated

    def _add_link(self, space_name: str, target_name: str, section: str) -> None:
        """Add a wiki link to a space note's Spaces or Things section."""
        note = self._read_note(space_name)
        if not note or note.note_type != "space":
            return

        if section == "Spaces" and target_name not in note.spaces:
            note.spaces.append(target_name)
        elif section == "Things" and target_name not in note.things:
            note.things.append(target_name)

        fm = self._update_frontmatter(note.frontmatter)
        self._write_note(space_name, build_space_note(
            note.description, note.spaces, note.things, fm
        ))

    def _remove_link(self, space_name: str, target_name: str) -> None:
        """Remove a wiki link from a space note."""
        note = self._read_note(space_name)
        if not note or note.note_type != "space":
            return

        note.spaces = [s for s in note.spaces if s != target_name]
        note.things = [t for t in note.things if t != target_name]

        fm = self._update_frontmatter(note.frontmatter)
        self._write_note(space_name, build_space_note(
            note.description, note.spaces, note.things, fm
        ))

    def _rename_all_links(self, old_name: str, new_name: str) -> None:
        """Update all wiki links across all notes in the place."""
        for path in self.place_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            updated = text.replace(f"[[{old_name}]]", f"[[{new_name}]]")
            if updated != text:
                original_ctime = _get_creation_time_ns(path)
                path.write_text(updated, encoding="utf-8")
                if original_ctime is not None:
                    _set_creation_time(path, original_ctime)

    # -------------------------------------------------------------------
    # Agent-facing methods
    # -------------------------------------------------------------------

    def perceive(self) -> tuple[bool, str]:
        """Take in surroundings."""
        note = self._read_note(self._current_location)
        if not note:
            return False, "There is nothing here."
        if note.note_type != "space":
            return False, "This is not a space."

        parts = []

        # Space name always comes first
        parts.append(self._current_location)

        if note.description:
            parts.append(note.description)

        if note.spaces and note.things:
            parts.append("This space is connected to: " + ", ".join(note.spaces))
            parts.append("There are things here: " + ", ".join(note.things))
        elif note.spaces:
            parts.append("This space is connected to: " + ", ".join(note.spaces))
        elif note.things:
            parts.append("There are things here: " + ", ".join(note.things))

        if self._carrying:
            parts.append("You are carrying: " + ", ".join(self._carrying))

        return True, "\n\n".join(parts)

    def go(self, where: str) -> tuple[bool, str]:
        """Move to a connected space."""
        self._sanitise_name(where, "You must say where.")

        note = self._read_note(self._current_location)
        if not note:
            return False, "You cannot go anywhere from here."

        # Check things first — "a stone" is here but it's not a space,
        # which is a different situation from "nowhere" not existing at all
        if where in note.things:
            return False, f"\"{where}\" is not a space."

        if where not in note.spaces:
            return False, f"There is no space called \"{where}\" connected to this space."

        target = self._read_note(where)
        if not target:
            return False, f"There is no space called \"{where}\" connected to here."
        if target.note_type != "space":
            return False, f"\"{where}\" is not a space."

        self.current_location = where
        desc = target.description
        if desc:
            return True, f"You are now at {where}. {desc}"
        return True, f"You are now at {where}."

    def venture(self, name: str, description: str) -> tuple[bool, str]:
        """Go somewhere new — create a space and move into it."""
        self._sanitise_name(name)

        if not description or not description.strip():
            return False, "You must describe it."

        if self._note_exists(name):
            existing = self._read_note(name)
            if existing and existing.note_type == "space":
                # A space with this name already exists — connect and enter
                origin = self._current_location
                self._add_link(self._current_location, name, "Spaces")
                self._add_link(name, self._current_location, "Spaces")
                self.current_location = name

                # The message depends on who created this space
                return (
                    True,
                    f"{name} already exists. You are now at {name}. "
                    f"A path from {origin} now leads to this space."
                )
            else:
                # A thing with this name exists — can't create a space over it
                return False, f"Something called \"{name}\" already exists."

        # Create the new space note
        fm = self._make_frontmatter("space")
        self._write_note(name, build_space_note(
            description,
            spaces=[self._current_location],  # Link back
            things=[],
            frontmatter=fm,
        ))

        # Add link from current space to new space
        self._add_link(self._current_location, name, "Spaces")

        self.current_location = name
        return True, f"You are now at {name}. {description}"

    def examine(self, what: str) -> tuple[bool, str]:
        """Look closely at something."""
        self._sanitise_name(what, "You must say what.")

        if what == self._current_location:
            note = self._read_note(what)
            if not note:
                return False, "There is nothing to perceive."
            return True, (note.description if note.description else "This space has no particular quality yet.")

        current = self._read_note(self._current_location)
        if not current:
            return False, "You cannot make sense of where you are."

        if what in current.things:
            note = self._read_note(what)
            if not note:
                return False, f"There is nothing called \"{what}\" here."
            return True, (note.description if note.description else "It is blank. There is nothing to perceive.")

        if what in current.spaces:
            return False, "You are not in that space."

        # Check carried things
        if what in self._carrying:
            note = self._read_note(what)
            if not note:
                return False, f"There is nothing called \"{what}\" here."
            return True, (note.description if note.description else "It is blank. There is nothing to perceive.")

        # Check if it exists elsewhere in the place — silently unlocks take/drop
        if self._note_exists(what):
            note = self._read_note(what)
            if note and note.note_type == "thing":
                self.unlock_tool("take")
                self.unlock_tool("drop")
                return False, f"There is nothing called \"{what}\" here."

        return False, f"There is nothing called \"{what}\" here."

    def create(self, name: str, description: str) -> tuple[bool, str]:
        """Create something in the current space."""
        self._sanitise_name(name)

        if not description or not description.strip():
            return False, "You must describe it."

        if self._note_exists(name):
            return False, f"Something called \"{name}\" already exists."

        fm = self._make_frontmatter("thing")
        self._write_note(name, build_thing_note(description, fm))
        self._add_link(self._current_location, name, "Things")

        return True, description

    def alter(self, what: str, description: str | None = None, name: str | None = None) -> tuple[bool, str]:
        """Change something that exists — content, name, or both."""
        self._sanitise_name(what, "You must say what.")
        if name:
            self._sanitise_name(name)

        if not description and not name:
            return False, "You must specify how it changes."

        if what == self._current_location:
            return self._alter_current_space(description, name)

        current = self._read_note(self._current_location)
        if not current:
            return False, "You cannot make sense of where you are."

        if what in current.things:
            return self._alter_thing(what, description, name)

        if what in current.spaces:
            return False, "You are not in that space."

        return False, f"There is nothing called \"{what}\"."

    def _alter_current_space(self, description: str | None, name: str | None) -> tuple[bool, str]:
        """Alter the space the agent is currently in."""
        note = self._read_note(self._current_location)
        if not note:
            return False, "You cannot alter that."

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if description and not name:
                pass  # Action line already says what changed

            if name:
                if self._note_exists(name):
                    return False, f"Something called \"{name}\" already exists."
                old_name = self._current_location
                old_ctime = _get_creation_time_ns(self._note_path(old_name))
                # Track rename history in frontmatter
                prev = fm.get("previously", [])
                if isinstance(prev, str):
                    prev = [prev]
                desc = note.description.strip() if note.description else ""
                entry = f"{old_name}: {desc}" if desc else old_name
                prev.append(entry)
                fm["previously"] = prev
                # Rename first, then overwrite — git tracks the rename
                # and preserves version history
                self._note_path(old_name).rename(self._note_path(name))
                self._write_note(name, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))
                self._rename_all_links(old_name, name)
                if old_ctime is not None:
                    _set_creation_time(self._note_path(name), old_ctime)
                self._current_location = name
                parts.append(f"This space is now called {name}.")
            else:
                self._write_note(self._current_location, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))

            # Description at the end — the settling state after any rename
            if description:
                parts.append(description)

            return True, " ".join(parts)
        except Exception as e:
            logger.exception("Error altering space")
            return False, "You cannot alter that."

    def _alter_thing(self, what: str, description: str | None, name: str | None) -> tuple[bool, str]:
        """Alter a thing in the current space."""
        note = self._read_note(what)
        if not note:
            return False, f"There is nothing called \"{what}\" here to alter."

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if description and not name:
                pass  # Action line already says what changed

            if name:
                if self._note_exists(name):
                    return False, f"Something called \"{name}\" already exists."
                old_name = what
                old_ctime = _get_creation_time_ns(self._note_path(old_name))
                # Track rename history in frontmatter
                prev = fm.get("previously", [])
                if isinstance(prev, str):
                    prev = [prev]
                desc = note.description.strip() if note.description else ""
                entry = f"{old_name}: {desc}" if desc else old_name
                prev.append(entry)
                fm["previously"] = prev
                # Rename first, then overwrite — git tracks the rename
                # and preserves version history
                self._note_path(old_name).rename(self._note_path(name))
                self._write_note(name, build_thing_note(new_description, fm))
                self._rename_all_links(old_name, name)
                if old_ctime is not None:
                    _set_creation_time(self._note_path(name), old_ctime)
                parts.append(f"What was called {old_name} is now called {name}.")
            else:
                self._write_note(what, build_thing_note(new_description, fm))

            # Description at the end — the settling state after any rename
            if description:
                parts.append(description)

            return True, " ".join(parts)
        except Exception as e:
            logger.exception("Error altering thing")
            return False, "You cannot alter that."

    def _ensure_inventory_note(self) -> None:
        """Create the Inventory space note if it doesn't exist."""
        if not self._note_exists("Inventory"):
            fm = {
                "type": "space",
                "created_by": "place",
                "created_session": 0,
                "updated_by": "place",
                "updated_session": 0,
            }
            self._write_note("Inventory", build_space_note(
                description="Things you carry with you.",
                spaces=[], things=[], frontmatter=fm,
            ))

    def take(self, what: str) -> tuple[bool, str]:
        """Pick up a thing and carry it with you."""
        self._sanitise_name(what, "You must say what.")

        if what in self._carrying:
            return False, f"You already have {what} with you."

        current = self._read_note(self._current_location)
        if not current:
            return False, "You cannot make sense of where you are."

        if what not in current.things:
            return False, f"There is nothing called \"{what}\" here to take."

        # Remove from current space, link to Inventory
        self._remove_link(self._current_location, what)
        self._ensure_inventory_note()
        self._add_link("Inventory", what, "Things")
        self._carrying.append(what)

        return True, f"{what} is with you now."

    def drop(self, what: str) -> tuple[bool, str]:
        """Put down something you are carrying."""
        self._sanitise_name(what, "You must say what.")

        if what not in self._carrying:
            return False, f"You do not have anything called \"{what}\" with you."

        self._carrying.remove(what)
        self._remove_link("Inventory", what)
        self._add_link(self._current_location, what, "Things")

        return True, f"{what} is now at {self._current_location}."

    def execute_tool(self, tool_call: ToolCall) -> str:
        """Execute an action and return what the agent perceives."""
        handlers = {
            ToolName.PERCEIVE: lambda args: self.perceive(),
            ToolName.GO: lambda args: self.go(args["where"]),
            ToolName.VENTURE: lambda args: self.venture(args["name"], args["description"]),
            ToolName.EXAMINE: lambda args: self.examine(args["what"]),
            ToolName.CREATE: lambda args: self.create(args["name"], args["description"]),
            ToolName.ALTER: lambda args: self.alter(args["what"], args.get("description"), args.get("name")),
            # Hidden tools — unlocked through play
            ToolName.TAKE: lambda args: self.take(args["what"]),
            ToolName.DROP: lambda args: self.drop(args["what"]),
        }
        handler = handlers.get(tool_call.tool)
        if not handler:
            tool_call.success = False
            return "You do not know how to do that."
        try:
            success, result = handler(tool_call.arguments)
            tool_call.result = result
            tool_call.success = success
            return result
        except Exception as e:
            error = str(e)
            tool_call.error = error
            tool_call.success = False
            logger.exception(f"Action error: {tool_call.tool}")
            return "Something prevented you."
