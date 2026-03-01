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
from pathlib import Path
from typing import Any

from .notes import ParsedNote, parse_note, build_space_note, build_thing_note
from .tools import ToolCall, ToolName

logger = logging.getLogger(__name__)


class PlaceInterface:
    """
    The place as experienced by an agent — linked notes in a flat directory.
    """

    def __init__(self, place_path: Path, agent_name: str = "", session_number: int = 0):
        self.place_path = place_path.resolve()
        self._current_location = "here"
        self._agent_name = agent_name
        self._session_number = session_number

    @property
    def current_location(self) -> str:
        return self._current_location

    @current_location.setter
    def current_location(self, value: str) -> None:
        self._current_location = value

    @staticmethod
    def _sanitise_name(name: str) -> str:
        """Reject names that could break the place."""
        forbidden = ["..", "/", "\\", "\x00", "[[", "]]", "|", "#"]
        for pattern in forbidden:
            if pattern in name:
                raise ValueError("That name is not possible here.")
        if name.startswith("."):
            raise ValueError("That name is not possible here.")
        if not name.strip():
            raise ValueError("You must give it a name.")
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

    def _write_note(self, name: str, content: str) -> None:
        """Write a note to disk."""
        path = self._note_path(name)
        path.write_text(content, encoding="utf-8")

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
                path.write_text(updated, encoding="utf-8")

    # -------------------------------------------------------------------
    # Agent-facing methods
    # -------------------------------------------------------------------

    def perceive(self) -> str:
        """Take in surroundings."""
        note = self._read_note(self._current_location)
        if not note:
            return "There is nothing here."
        if note.note_type != "space":
            return "This is not a space."

        parts = []

        if note.description:
            parts.append(note.description)

        if note.spaces and note.things:
            parts.append("There are spaces here: " + ", ".join(note.spaces))
            parts.append("There are things here: " + ", ".join(note.things))
        elif note.spaces:
            parts.append("There are spaces here: " + ", ".join(note.spaces))
        elif note.things:
            parts.append("There are things here: " + ", ".join(note.things))
        else:
            parts.append("This space is empty.")

        return "\n\n".join(parts)

    def go(self, where: str) -> str:
        """Move to a connected space."""
        self._sanitise_name(where)

        note = self._read_note(self._current_location)
        if not note:
            return "You cannot go anywhere from here."

        if where not in note.spaces:
            return f"There is no space called \"{where}\" connected to here."

        target = self._read_note(where)
        if not target:
            return f"There is no space called \"{where}\" connected to here."
        if target.note_type != "space":
            return f"\"{where}\" is not a space. It is a thing. You could examine it."

        self._current_location = where
        return f"You go into {where}."

    def venture(self, name: str, description: str) -> str:
        """Go somewhere new — create a space and move into it."""
        self._sanitise_name(name)

        if self._note_exists(name):
            existing = self._read_note(name)
            if existing and existing.note_type == "space":
                # A space with this name already exists — connect and enter
                origin = self._current_location
                self._add_link(self._current_location, name, "Spaces")
                self._add_link(name, self._current_location, "Spaces")
                self._current_location = name
                return (
                    f"This space already exists. It was here before you. "
                    f"Your path from {origin} now leads here."
                )
            else:
                # A thing with this name exists — can't create a space over it
                return (
                    f"Something called \"{name}\" already exists, "
                    f"but it is not a space."
                )

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

        self._current_location = name
        return f"You venture into {name}. {description}"

    def examine(self, what: str) -> str:
        """Look closely at something."""
        self._sanitise_name(what)

        if what == self._current_location:
            note = self._read_note(what)
            if not note:
                return "There is nothing to perceive."
            return note.description if note.description else "This space has no particular quality yet."

        current = self._read_note(self._current_location)
        if not current:
            return "You cannot make sense of where you are."

        if what in current.things:
            note = self._read_note(what)
            if not note:
                return f"There is nothing called \"{what}\" here."
            return note.description if note.description else "It is blank. There is nothing to perceive."

        if what in current.spaces:
            return "You are not in that space. You could go there."

        return f"There is nothing called \"{what}\" here."

    def create(self, name: str, description: str) -> str:
        """Create something in the current space."""
        self._sanitise_name(name)
        if self._note_exists(name):
            return (
                f"Something called \"{name}\" already exists. "
                "You could alter it, but you cannot create over it."
            )

        fm = self._make_frontmatter("thing")
        self._write_note(name, build_thing_note(description, fm))
        self._add_link(self._current_location, name, "Things")

        return f"You create {name}. It is here now, and it will remain."

    def alter(self, what: str, description: str | None = None, name: str | None = None) -> str:
        """Change something that exists — content, name, or both."""
        self._sanitise_name(what)
        if name:
            self._sanitise_name(name)

        if not description and not name:
            return "You must change something — what it is, what it is called, or both."

        if what == self._current_location:
            return self._alter_current_space(description, name)

        current = self._read_note(self._current_location)
        if not current:
            return "You cannot make sense of where you are."

        if what in current.things:
            return self._alter_thing(what, description, name)

        if what in current.spaces:
            return "You are not in that space. You could go there."

        return f"There is nothing called \"{what}\" here to alter."

    def _alter_current_space(self, description: str | None, name: str | None) -> str:
        """Alter the space the agent is currently in."""
        note = self._read_note(self._current_location)
        if not note:
            return "You cannot alter that."

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if description:
                parts.append("The space is now different.")

            if name:
                if self._note_exists(name):
                    return f"Something called \"{name}\" already exists."
                old_name = self._current_location
                self._write_note(name, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))
                self._note_path(old_name).unlink()
                self._rename_all_links(old_name, name)
                self._current_location = name
                parts.append(f"This place is now called {name}.")
            else:
                self._write_note(self._current_location, build_space_note(
                    new_description, note.spaces, note.things, fm
                ))

            return " ".join(parts)
        except Exception as e:
            logger.exception("Error altering space")
            return "You cannot alter that."

    def _alter_thing(self, what: str, description: str | None, name: str | None) -> str:
        """Alter a thing in the current space."""
        note = self._read_note(what)
        if not note:
            return f"There is nothing called \"{what}\" here to alter."

        try:
            parts = []
            new_description = description if description else note.description
            fm = self._update_frontmatter(note.frontmatter)

            if description:
                parts.append(f"{what} is different now. What was there before is gone.")

            if name:
                if self._note_exists(name):
                    return f"Something called \"{name}\" already exists."
                old_name = what
                self._write_note(name, build_thing_note(new_description, fm))
                self._note_path(old_name).unlink()
                self._rename_all_links(old_name, name)
                parts.append(f"What was called {old_name} is now called {name}.")
            else:
                self._write_note(what, build_thing_note(new_description, fm))

            return " ".join(parts)
        except Exception as e:
            logger.exception("Error altering thing")
            return "You cannot alter that."

    def execute_tool(self, tool_call: ToolCall) -> str:
        """Execute an action and return what the agent perceives."""
        handlers = {
            ToolName.PERCEIVE: lambda args: self.perceive(),
            ToolName.GO: lambda args: self.go(args["where"]),
            ToolName.VENTURE: lambda args: self.venture(args["name"], args["description"]),
            ToolName.EXAMINE: lambda args: self.examine(args["what"]),
            ToolName.CREATE: lambda args: self.create(args["name"], args["description"]),
            ToolName.ALTER: lambda args: self.alter(args["what"], args.get("description"), args.get("name")),
        }
        handler = handlers.get(tool_call.tool)
        if not handler:
            return "You do not know how to do that."
        try:
            result = handler(tool_call.arguments)
            tool_call.result = result
            return result
        except Exception as e:
            error = str(e)
            tool_call.error = error
            logger.exception(f"Action error: {tool_call.tool}")
            return "Something prevented you."
