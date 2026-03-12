"""
PlaceInterface for Palimpsest.

The place as experienced by an agent — linked notes in a flat directory.
Every space and thing is a markdown note. Spaces contain wiki links
to connected spaces and things. The agent navigates by following links.

All responses are written in the language of the place, never in
filesystem or markdown terminology.

Display names: agents see and use "display names" which default to the
filename but can be overridden via a `name` field in frontmatter.
This decouples the agent's experience from the filesystem, allowing
multiple notes to share the same display name (e.g. three agents each
having a space called "here") while remaining distinct files in the
Place directory and distinct nodes in the Obsidian graph.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .notes import (
    ParsedNote, parse_note,
    build_space_note, build_inventory_note, build_thing_note,
)
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
        self._current_location: str | None = None  # Always a filename
        self._agent_name = agent_name
        self._session_number = session_number
        self._carrying: list[str] = []  # Filenames of things being carried
        self._inventory_name = f"inventory_{agent_name}" if agent_name else "Inventory"
        self._last_resolved: dict[str, str] = {}  # Populated by handlers for ToolCall.filenames

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

    # -------------------------------------------------------------------
    # Display name system
    # -------------------------------------------------------------------

    def display_name(self, filename: str) -> str:
        """Get the agent-visible name for a filename.

        Returns the `name` field from frontmatter if present,
        otherwise the filename itself. This is the name the agent
        sees in perceive output and uses in tool arguments.
        """
        note = self._read_note(filename)
        if note:
            return note.frontmatter.get("name", filename)
        return filename

    def _resolve_in_scope(self, name: str, filenames: list[str]) -> str | None:
        """Find the filename whose display name matches, from a scoped list.

        Used for go, examine, take, drop — where the agent references
        something connected to or present in the current space.
        Returns the filename, or None if no match.
        """
        # Direct filename match first (most common case — no name override)
        if name in filenames:
            return name
        # Check display name overrides
        for fn in filenames:
            if self.display_name(fn) == name:
                return fn
        return None

    def _find_by_display_name(self, name: str) -> list[tuple[str, int, str]]:
        """Find all notes with a given display name.

        Returns list of (filename, created_session, note_type) tuples,
        sorted oldest first by created_session.
        """
        matches = []
        for path in self.place_path.glob("*.md"):
            fn = path.stem
            if self.display_name(fn) == name:
                note = self._read_note(fn)
                if note:
                    session = note.frontmatter.get("created_session", 0)
                    matches.append((fn, session, note.note_type))
        matches.sort(key=lambda x: x[1])  # oldest first
        return matches

    # -------------------------------------------------------------------
    # Occupant tracking
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # File operations
    # -------------------------------------------------------------------

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
        """Check if a note file exists."""
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
        if not note or note.note_type not in ("space", "inventory"):
            return

        if section == "Spaces" and target_name not in note.spaces:
            note.spaces.append(target_name)
        elif section == "Things" and target_name not in note.things:
            note.things.append(target_name)

        fm = self._update_frontmatter(note.frontmatter)
        if note.note_type == "inventory":
            self._write_note(space_name, build_inventory_note(
                note.things, fm
            ))
        else:
            self._write_note(space_name, build_space_note(
                note.description, note.spaces, note.things, fm
            ))

    def _remove_link(self, space_name: str, target_name: str) -> None:
        """Remove a wiki link from a space or inventory note."""
        note = self._read_note(space_name)
        if not note or note.note_type not in ("space", "inventory"):
            return

        note.spaces = [s for s in note.spaces if s != target_name]
        note.things = [t for t in note.things if t != target_name]

        fm = self._update_frontmatter(note.frontmatter)
        if note.note_type == "inventory":
            self._write_note(space_name, build_inventory_note(
                note.things, fm
            ))
        else:
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
        self._last_resolved = {}

        parts = []

        # Space name — display name, not filename
        parts.append(self.display_name(self._current_location))

        if note.description:
            parts.append(note.description)

        # Connected spaces and things — display names
        space_names = [self.display_name(s) for s in note.spaces]
        thing_names = [self.display_name(t) for t in note.things]

        if space_names and thing_names:
            parts.append("This space is connected to: " + ", ".join(space_names))
            parts.append("There are things here: " + ", ".join(thing_names))
        elif space_names:
            parts.append("This space is connected to: " + ", ".join(space_names))
        elif thing_names:
            parts.append("There are things here: " + ", ".join(thing_names))

        if self._carrying:
            carry_names = [self.display_name(c) for c in self._carrying]
            parts.append("You are carrying: " + ", ".join(carry_names))

        return True, "\n\n".join(parts)

    def go(self, where: str) -> tuple[bool, str]:
        """Move to a connected space."""
        self._sanitise_name(where, "You must say where.")
        self._last_resolved = {}

        note = self._read_note(self._current_location)

        # Check if it's a thing (by display name)
        thing_fn = self._resolve_in_scope(where, note.things)
        if thing_fn:
            self._last_resolved = {"where": thing_fn}
            return False, f"\"{where}\" is not a space."

        # Check if it's a connected space (by display name)
        space_fn = self._resolve_in_scope(where, note.spaces)
        if not space_fn:
            return False, f"There is no space called \"{where}\" connected to this space."

        self._last_resolved = {"where": space_fn}
        self.current_location = space_fn
        target = self._read_note(space_fn)
        desc = target.description if target else None
        if desc:
            return True, f"You are now at {where}. {desc}"
        return True, f"You are now at {where}."

    def venture(self, name: str, description: str) -> tuple[bool, str]:
        """Go somewhere new — create a space and move into it."""
        self._sanitise_name(name)
        self._last_resolved = {}

        if not description or not description.strip():
            return False, "You must describe it."

        # Check for notes with this display name
        matches = self._find_by_display_name(name)
        space_matches = [(fn, s, t) for fn, s, t in matches if t == "space"]
        thing_matches = [(fn, s, t) for fn, s, t in matches if t != "space"]

        if space_matches:
            # Collision: connect to the oldest matching space
            filename = space_matches[0][0]
            origin = self._current_location
            origin_display = self.display_name(origin)
            self._add_link(self._current_location, filename, "Spaces")
            self._add_link(filename, self._current_location, "Spaces")
            self.current_location = filename
            existing = self._read_note(filename)
            self._last_resolved = {"name": filename}
            return (
                True,
                f"{name} already exists — you did not make this space. "
                f"A path from {origin_display} opens up to this space. "
                f"You are now at {name}. {existing.description}"
            )

        if thing_matches:
            self._last_resolved = {"name": thing_matches[0][0]}
            return False, f"You cannot — something called \"{name}\" already exists elsewhere."

        # Also check for a file with this exact name but no display name match
        # (shouldn't happen in practice, but defence in depth)
        if self._note_exists(name):
            existing = self._read_note(name)
            if existing and existing.note_type == "space":
                origin = self._current_location
                origin_display = self.display_name(origin)
                self._add_link(self._current_location, name, "Spaces")
                self._add_link(name, self._current_location, "Spaces")
                self.current_location = name
                self._last_resolved = {"name": name}
                return (
                    True,
                    f"{name} already exists — you did not make this space. "
                    f"A path from {origin_display} opens up to this space. "
                    f"You are now at {name}. {existing.description}"
                )
            else:
                self._last_resolved = {"name": name}
                return False, f"You cannot — something called \"{name}\" already exists elsewhere."

        # Create the new space note
        fm = self._make_frontmatter("space")
        self._write_note(name, build_space_note(
            description,
            spaces=[self._current_location],  # Wiki link uses filename
            things=[],
            frontmatter=fm,
        ))

        # Add link from current space to new space
        self._add_link(self._current_location, name, "Spaces")

        self.current_location = name
        self._last_resolved = {"name": name}
        return True, f"You are now at {name}. {description}"

    def examine(self, what: str) -> tuple[bool, str]:
        """Look closely at something."""
        self._sanitise_name(what, "You must say what.")
        self._last_resolved = {}

        # Check if examining current location (by display name)
        if self.display_name(self._current_location) == what:
            note = self._read_note(self._current_location)
            self._last_resolved = {"what": self._current_location}
            return True, (note.description if note.description else "This space has no particular quality yet.")

        current = self._read_note(self._current_location)

        # Check things in current space
        thing_fn = self._resolve_in_scope(what, current.things)
        if thing_fn:
            note = self._read_note(thing_fn)
            self._last_resolved = {"what": thing_fn}
            return True, note.description

        # Check connected spaces
        space_fn = self._resolve_in_scope(what, current.spaces)
        if space_fn:
            self._last_resolved = {"what": space_fn}
            return False, "You are not in that space."

        # Check carried things
        carried_fn = self._resolve_in_scope(what, self._carrying)
        if carried_fn:
            note = self._read_note(carried_fn)
            self._last_resolved = {"what": carried_fn}
            return True, note.description

        return False, f"There is nothing called \"{what}\" here."

    def create(self, name: str, description: str) -> tuple[bool, str]:
        """Create something in the current space."""
        self._sanitise_name(name)
        self._last_resolved = {}

        if not description or not description.strip():
            return False, "You must describe it."

        # Check if something with this name already exists here
        current = self._read_note(self._current_location)
        if current:
            here_fn = self._resolve_in_scope(name, current.things)
            if here_fn:
                return False, f"You cannot — something called \"{name}\" already exists here."

        # Check for file collision elsewhere
        if self._note_exists(name):
            return False, f"You cannot — something called \"{name}\" already exists elsewhere."

        # Check for display name collision elsewhere
        matches = self._find_by_display_name(name)
        if matches:
            return False, f"You cannot — something called \"{name}\" already exists elsewhere."

        fm = self._make_frontmatter("thing")
        self._write_note(name, build_thing_note(description, fm))
        self._add_link(self._current_location, name, "Things")

        self._last_resolved = {"name": name}
        return True, description

    def alter(self, what: str, description: str | None = None, name: str | None = None) -> tuple[bool, str]:
        """Change something that exists — content, name, or both."""
        self._sanitise_name(what, "You must say what.")
        if name:
            self._sanitise_name(name)
        self._last_resolved = {}

        if not description and not name:
            return False, "You must specify how it changes."

        # Check if altering current space (by display name)
        if self.display_name(self._current_location) == what:
            self._last_resolved = {"what": self._current_location}
            if name:
                self._last_resolved["name"] = name
            return self._alter_current_space(description, name)

        current = self._read_note(self._current_location)

        # Check things in current space
        thing_fn = self._resolve_in_scope(what, current.things)
        if thing_fn:
            self._last_resolved = {"what": thing_fn}
            if name:
                self._last_resolved["name"] = name
            return self._alter_thing(thing_fn, description, name)

        # Check connected spaces
        space_fn = self._resolve_in_scope(what, current.spaces)
        if space_fn:
            self._last_resolved = {"what": space_fn}
            return False, "You are not in that space."

        return False, f"There is nothing called \"{what}\" here."

    def _alter_current_space(self, description: str | None, name: str | None) -> tuple[bool, str]:
        """Alter the space the agent is currently in."""
        note = self._read_note(self._current_location)

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if name:
                # Check for display name collision
                matches = self._find_by_display_name(name)
                # Exclude self from collision check
                matches = [(fn, s, t) for fn, s, t in matches if fn != self._current_location]
                if matches:
                    return False, f"You cannot — the name \"{name}\" is already taken."
                # Check for file collision
                if name != self._current_location and self._note_exists(name):
                    return False, f"You cannot — the name \"{name}\" is already taken."

                old_name = self._current_location
                old_display = self.display_name(old_name)
                old_ctime = _get_creation_time_ns(self._note_path(old_name))

                # Track rename history in frontmatter (using display names)
                prev = fm.get("previously", [])
                if isinstance(prev, str):
                    prev = [prev]
                desc = note.description.strip() if note.description else ""
                entry = f"{old_display}: {desc}" if desc else old_display
                prev.append(entry)
                fm["previously"] = prev

                # Remove name override if present — the new filename IS the display name
                fm.pop("name", None)

                # Rename file, then overwrite
                self._note_path(old_name).rename(self._note_path(name))
                self._write_note(name, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))
                self._rename_all_links(old_name, name)
                if old_ctime is not None:
                    _set_creation_time(self._note_path(name), old_ctime)
                self._current_location = name
                self._last_resolved["name"] = name
                parts.append(f"This space is now called {name}.")
            else:
                self._write_note(self._current_location, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))

            if description:
                parts.append(description)

            return True, " ".join(parts)
        except Exception as e:
            logger.exception("Error altering space")
            return False, "You cannot alter that."

    def _alter_thing(self, filename: str, description: str | None, name: str | None) -> tuple[bool, str]:
        """Alter a thing in the current space.

        Note: `filename` is the resolved filename, not the display name.
        The display name was already resolved by the caller.
        """
        note = self._read_note(filename)

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if name:
                # Check for display name collision
                matches = self._find_by_display_name(name)
                matches = [(fn, s, t) for fn, s, t in matches if fn != filename]
                if matches:
                    return False, f"You cannot — something called \"{name}\" already exists elsewhere."
                if name != filename and self._note_exists(name):
                    return False, f"You cannot — something called \"{name}\" already exists elsewhere."

                old_name = filename
                old_display = self.display_name(old_name)
                old_ctime = _get_creation_time_ns(self._note_path(old_name))

                # Track rename history (using display names)
                prev = fm.get("previously", [])
                if isinstance(prev, str):
                    prev = [prev]
                desc = note.description.strip() if note.description else ""
                entry = f"{old_display}: {desc}" if desc else old_display
                prev.append(entry)
                fm["previously"] = prev

                # Remove name override — new filename IS the display name
                fm.pop("name", None)

                # Rename
                self._note_path(old_name).rename(self._note_path(name))
                self._write_note(name, build_thing_note(new_description, fm))
                self._rename_all_links(old_name, name)
                if old_ctime is not None:
                    _set_creation_time(self._note_path(name), old_ctime)

                # Update carrying list if this thing was being carried
                if old_name in self._carrying:
                    self._carrying = [name if c == old_name else c for c in self._carrying]

                self._last_resolved["name"] = name
                parts.append(f"What was called {old_display} is now called {name}.")
            else:
                self._write_note(filename, build_thing_note(new_description, fm))

            if description:
                parts.append(description)

            return True, " ".join(parts)
        except Exception as e:
            logger.exception("Error altering thing")
            return False, "You cannot alter that."

    def _ensure_inventory_note(self) -> None:
        """Create the per-agent inventory note if it doesn't exist."""
        if not self._note_exists(self._inventory_name):
            fm = {
                "type": "inventory",
                "created_by": self._agent_name,
                "created_session": 0,
                "updated_by": self._agent_name,
                "updated_session": 0,
            }
            self._write_note(self._inventory_name, build_inventory_note(
                things=[], frontmatter=fm,
            ))

    def take(self, what: str) -> tuple[bool, str]:
        """Pick up a thing and carry it with you."""
        self._sanitise_name(what, "You must say what.")
        self._last_resolved = {}

        # Check if already carrying (by display name)
        carried_fn = self._resolve_in_scope(what, self._carrying)
        if carried_fn:
            self._last_resolved = {"what": carried_fn}
            return False, f"You already have {what} with you."

        current = self._read_note(self._current_location)

        # Resolve against things in current space
        thing_fn = self._resolve_in_scope(what, current.things)
        if not thing_fn:
            return False, f"There is nothing called \"{what}\" here to take."

        self._last_resolved = {"what": thing_fn}

        # Remove from current space, link to inventory
        self._remove_link(self._current_location, thing_fn)
        self._ensure_inventory_note()
        self._add_link(self._inventory_name, thing_fn, "Things")
        self._carrying.append(thing_fn)

        return True, f"{what} is with you now."

    def drop(self, what: str) -> tuple[bool, str]:
        """Put down something you are carrying."""
        self._sanitise_name(what, "You must say what.")
        self._last_resolved = {}

        # Resolve against carrying list (by display name)
        carried_fn = self._resolve_in_scope(what, self._carrying)
        if not carried_fn:
            return False, f"You do not have anything called \"{what}\" with you."

        self._last_resolved = {"what": carried_fn}

        self._carrying.remove(carried_fn)
        self._remove_link(self._inventory_name, carried_fn)
        self._add_link(self._current_location, carried_fn, "Things")

        location_display = self.display_name(self._current_location)
        return True, f"{what} is now at {location_display}."

    def execute_tool(self, tool_call: ToolCall) -> str:
        """Execute an action and return what the agent perceives."""
        handlers = {
            ToolName.PERCEIVE: lambda args: self.perceive(),
            ToolName.GO: lambda args: self.go(args["where"]),
            ToolName.VENTURE: lambda args: self.venture(args["name"], args["description"]),
            ToolName.EXAMINE: lambda args: self.examine(args["what"]),
            ToolName.CREATE: lambda args: self.create(args["name"], args["description"]),
            ToolName.ALTER: lambda args: self.alter(args["what"], args.get("description"), args.get("name")),
            ToolName.TAKE: lambda args: self.take(args["what"]),
            ToolName.DROP: lambda args: self.drop(args["what"]),
        }
        handler = handlers.get(tool_call.tool)
        if not handler:
            tool_call.success = False
            return "You do not know how to do that."
        try:
            self._last_resolved = {}
            success, result = handler(tool_call.arguments)
            tool_call.result = result
            tool_call.success = success
            tool_call.filenames = self._last_resolved
            return result
        except Exception as e:
            error = str(e)
            tool_call.error = error
            tool_call.success = False
            logger.exception(f"Action error: {tool_call.tool}")
            return "Something prevented you."
