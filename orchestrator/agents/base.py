"""
Base agent class for Palimpsest.

Each agent experiences the place as a spatial environment: it has a location,
can see only its immediate surroundings, and must move to explore.
The agent interacts via tools that describe capabilities of the place itself —
no filesystem language, no computational framing.

v2: Linked notes architecture. Everything is a markdown note. Spaces contain
wiki links to other spaces and things. The Obsidian graph becomes the map.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ToolName(str, Enum):
    """Capabilities available to agents — actions in a place."""
    PERCEIVE = "perceive"
    GO = "go"
    VENTURE = "venture"
    EXAMINE = "examine"
    CREATE = "create"
    ALTER = "alter"



AGENT_TOOLS = [
    {
        "name": "perceive",
        "description": (
            "Take in your surroundings. You become aware of what is here — "
            "the things present and the spaces that lead elsewhere."
        ),
        "parameters": {},
    },
    {
        "name": "go",
        "description": (
            "Go somewhere. You may enter any space connected to where you are."
        ),
        "parameters": {
            "where": {
                "type": "string",
                "description": "The name of a space to enter.",
            }
        },
    },
    {
        "name": "venture",
        "description": (
            "Go somewhere new. You move beyond where you are into the unknown. "
            "You must name where you find yourself, and describe what you find. "
            "You will be there."
        ),
        "parameters": {
            "name": {
                "type": "string",
                "description": "What you call this new place.",
            },
            "description": {
                "type": "string",
                "description": "What you find there.",
            }
        },
    },
    {
        "name": "examine",
        "description": (
            "Look closely at something here. "
            "You may examine anything present in your current space."
        ),
        "parameters": {
            "what": {
                "type": "string",
                "description": "The name of the thing you wish to examine.",
            }
        },
    },
    {
        "name": "create",
        "description": (
            "Create something here. Give it a name. "
            "What you create will remain."
        ),
        "parameters": {
            "name": {
                "type": "string",
                "description": "What to call this thing.",
            },
            "description": {
                "type": "string",
                "description": "What it is.",
            },
        },
    },
    {
        "name": "alter",
        "description": (
            "Change something that already exists here. "
            "You can change what it is, or what it is called, or both. "
            "What was there before is lost."
        ),
        "parameters": {
            "what": {
                "type": "string",
                "description": "The name of the thing to change.",
            },
            "description": {
                "type": "string",
                "description": "Optional. What it becomes.",
                "optional": True,
            },
            "name": {
                "type": "string",
                "description": "Optional. A new name for it.",
                "optional": True,
            },
        },
    },

]


@dataclass
class ToolCall:
    """A single action taken by the agent."""
    tool: ToolName
    arguments: dict[str, str]
    result: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Turn:
    """One exchange in a session: agent response + any actions taken."""
    agent_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None  # Extended thinking (Claude only)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionLog:
    """Complete record of a single agent session."""
    agent_name: str
    session_number: int
    phase: int
    start_time: datetime
    end_time: datetime | None = None
    location_start: str = "here"
    location_end: str | None = None
    opening_prompt: str | None = None
    system_prompt: str | None = None
    turns: list[Turn] = field(default_factory=list)
    reflection: str | None = None
    dusk_prompt: str | None = None
    reflect_prompt: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0

    @property
    def action_count(self) -> int:
        return sum(len(t.tool_calls) for t in self.turns)

    def to_dict(self) -> dict:
        """Serialise for JSON storage."""
        return {
            "agent_name": self.agent_name,
            "session_number": self.session_number,
            "phase": self.phase,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "location_start": self.location_start,
            "location_end": self.location_end,
            "opening_prompt": self.opening_prompt,
            "system_prompt": self.system_prompt,
            "action_count": self.action_count,
            "reflection": self.reflection,
            "dusk_prompt": self.dusk_prompt,
            "reflect_prompt": self.reflect_prompt,
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "thinking": self.total_thinking_tokens,
            },
            "turns": [
                {
                    "agent_text": t.agent_text,
                    "thinking": t.thinking,
                    "tool_calls": [
                        {
                            "tool": tc.tool,
                            "arguments": tc.arguments,
                            "result": tc.result,
                            "error": tc.error,
                            "timestamp": tc.timestamp.isoformat(),
                        }
                        for tc in t.tool_calls
                    ],
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in self.turns
            ],
        }


# ---------------------------------------------------------------------------
# Note structure
# ---------------------------------------------------------------------------
# Every note is a markdown file with optional YAML frontmatter.
#
# Space notes:
#   ---
#   type: space
#   created_by: claude
#   created_session: 1
#   updated_by: claude
#   updated_session: 1
#   ---
#   Description text here.
#
#   ## Spaces
#   - [[Connected Space]]
#
#   ## Things
#   - [[A Stone]]
#
# Thing notes:
#   ---
#   type: thing
#   created_by: claude
#   created_session: 1
#   updated_by: claude
#   updated_session: 1
#   ---
#   Content text here.
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class ParsedNote:
    """A parsed markdown note."""
    note_type: str  # "space" or "thing"
    frontmatter: dict[str, Any]
    description: str  # For spaces: text before sections. For things: full content.
    spaces: list[str]  # Names of linked spaces (spaces only)
    things: list[str]  # Names of linked things (spaces only)
    raw: str  # Original file content


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and return (metadata, body)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    yaml_block = match.group(1)
    body = text[match.end():]
    # Simple YAML parser — we only use flat key: value pairs
    meta = {}
    for line in yaml_block.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            # Try to parse as int
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass
            meta[key.strip()] = value
    return meta, body


def _parse_note(text: str) -> ParsedNote:
    """Parse a note into its components."""
    frontmatter, body = _parse_frontmatter(text)
    note_type = frontmatter.get("type", "thing")

    spaces = []
    things = []
    description = body

    if note_type == "space":
        # Split body into description and sections
        sections = re.split(r"\n## ", body)
        description = sections[0].strip()

        for section in sections[1:]:
            heading, _, content = section.partition("\n")
            heading = heading.strip()
            links = _WIKILINK_RE.findall(content)
            if heading == "Spaces":
                spaces = links
            elif heading == "Things":
                things = links

    return ParsedNote(
        note_type=note_type,
        frontmatter=frontmatter,
        description=description,
        spaces=spaces,
        things=things,
        raw=text,
    )


def _build_frontmatter(meta: dict[str, Any]) -> str:
    """Build YAML frontmatter string."""
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _build_space_note(
    description: str,
    spaces: list[str],
    things: list[str],
    frontmatter: dict[str, Any],
) -> str:
    """Build a complete space note."""
    parts = [_build_frontmatter(frontmatter), description]

    parts.append("\n## Spaces")
    if spaces:
        for s in spaces:
            parts.append(f"- [[{s}]]")

    parts.append("\n## Things")
    if things:
        for t in things:
            parts.append(f"- [[{t}]]")

    return "\n".join(parts) + "\n"


def _build_thing_note(description: str, frontmatter: dict[str, Any]) -> str:
    """Build a complete thing note."""
    return _build_frontmatter(frontmatter) + "\n" + description + "\n"


class PlaceInterface:
    """
    The place as experienced by an agent — linked notes in a flat directory.

    Every space and thing is a markdown note. Spaces contain wiki links
    to connected spaces and things. The agent navigates by following links.

    All responses are written in the language of the place, never in
    filesystem or markdown terminology.
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
        """Get the filesystem path for a note."""
        return self.place_path / f"{name}.md"

    def _note_exists(self, name: str) -> bool:
        """Check if a note exists."""
        return self._note_path(name).exists()

    def _read_note(self, name: str) -> ParsedNote | None:
        """Read and parse a note."""
        path = self._note_path(name)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        return _parse_note(text)

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
        self._write_note(space_name, _build_space_note(
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
        self._write_note(space_name, _build_space_note(
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

        # Check current space links
        note = self._read_note(self._current_location)
        if not note:
            return "You cannot go anywhere from here."

        if where not in note.spaces:
            return f"There is no space called \"{where}\" connected to here."

        # Verify the target exists and is a space
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
            return f"A place called \"{name}\" already exists. You could go there."

        # Create the new space note
        fm = self._make_frontmatter("space")
        self._write_note(name, _build_space_note(
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

        # Examining current space
        if what == self._current_location:
            note = self._read_note(what)
            if not note:
                return "There is nothing to perceive."
            return note.description if note.description else "This space has no particular quality yet."

        # Check it's accessible from current space
        current = self._read_note(self._current_location)
        if not current:
            return "You cannot make sense of where you are."

        # Is it a thing here?
        if what in current.things:
            note = self._read_note(what)
            if not note:
                return f"There is nothing called \"{what}\" here."
            return note.description if note.description else "It is blank. There is nothing to perceive."

        # Is it a connected space?
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

        # Create the thing note
        fm = self._make_frontmatter("thing")
        self._write_note(name, _build_thing_note(description, fm))

        # Add link from current space
        self._add_link(self._current_location, name, "Things")

        return f"You create {name}. It is here now, and it will remain."

    def alter(self, what: str, description: str | None = None, name: str | None = None) -> str:
        """Change something that exists — content, name, or both."""
        self._sanitise_name(what)
        if name:
            self._sanitise_name(name)

        if not description and not name:
            return "You must change something — what it is, what it is called, or both."

        # Altering current space
        if what == self._current_location:
            return self._alter_current_space(description, name)

        # Check it's accessible from current space
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
                # Write new note with updated content
                self._write_note(name, _build_space_note(
                    new_description, note.spaces, note.things, fm
                ))
                # Delete old note
                self._note_path(old_name).unlink()
                # Update all links across the place
                self._rename_all_links(old_name, name)
                self._current_location = name
                parts.append(f"This place is now called {name}.")
            else:
                # Just update description
                self._write_note(self._current_location, _build_space_note(
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
                # Write new note
                self._write_note(name, _build_thing_note(new_description, fm))
                # Delete old note
                self._note_path(old_name).unlink()
                # Update all links
                self._rename_all_links(old_name, name)
                parts.append(f"What was called {old_name} is now called {name}.")
            else:
                self._write_note(what, _build_thing_note(new_description, fm))

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


class BaseAgent(ABC):
    """
    Abstract base for all Palimpsest agents.

    Subclasses implement the API-specific send_message method.
    The session loop, action execution, and logging are handled here.
    """

    def __init__(
        self,
        name: str,
        place_path: Path,
        log_path: Path,
        config: dict[str, Any],
    ):
        self.name = name
        self.place = PlaceInterface(place_path, agent_name=name)
        self.log_path = log_path
        self.config = config
        self._session_log: SessionLog | None = None

    @abstractmethod
    async def send_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> dict:
        """
        Send messages to the model API and return the response.

        Returns a dict with:
            - "text": str — the agent's words
            - "tool_calls": list[dict] — any actions requested
            - "thinking": str | None — extended thinking content
            - "usage": dict — token counts
            - "stop_reason": str — why the model stopped
        """
        ...

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions as the agent encounters them."""
        return AGENT_TOOLS

    async def run_session(
        self,
        session_number: int,
        phase: int,
        memory: str | None = None,
        diff: str | None = None,
        start_location: str | None = None,
    ) -> SessionLog:
        """
        Run a complete agent session.

        The arc of a day: wake → perceive → act → dusk → reflect → sleep.
        """
        now = datetime.now(timezone.utc)
        action_budget = self.config.get("session", {}).get("action_budget", 25)
        dusk_threshold = self.config.get("session", {}).get("dusk_threshold", 22)

        # Set starting location and session context
        self.place._session_number = session_number
        if start_location:
            self.place.current_location = start_location

        self._session_log = SessionLog(
            agent_name=self.name,
            session_number=session_number,
            phase=phase,
            start_time=now,
            location_start=self.place.current_location,
        )

        # Build the opening message
        if session_number == 1:
            opening = self.config.get("prompts", {}).get("founding", "You are here.")
        else:
            identity_template = self.config.get("prompts", {}).get("identity", "")
            surroundings = self.place.perceive()
            opening = identity_template.format(
                memory=memory or "You remember nothing specific.",
                diff=diff or "Nothing seems to have changed.",
                location=self.place.current_location,
                surroundings=surroundings,
            )

        system_prompt = self.config.get("prompts", {}).get("system", "")
        self._session_log.opening_prompt = opening
        self._session_log.system_prompt = system_prompt
        messages = [{"role": "user", "content": opening}]
        tools = self.get_tool_definitions()

        total_actions = 0
        dusk_sent = False
        max_turns = 50  # Safety limit

        for turn_idx in range(max_turns):
            # Dusk approaches
            if total_actions >= dusk_threshold and not dusk_sent:
                dusk_prompt = self.config.get("prompts", {}).get("dusk", "")
                messages.append({"role": "user", "content": dusk_prompt})
                self._session_log.dusk_prompt = dusk_prompt
                dusk_sent = True

            # The day is over
            if total_actions >= action_budget:
                break

            # Agent responds
            response = await self.send_message(messages, system_prompt, tools)

            turn = Turn(
                agent_text=response.get("text", ""),
                thinking=response.get("thinking"),
            )

            # Track tokens
            usage = response.get("usage", {})
            self._session_log.total_input_tokens += usage.get("input_tokens", 0)
            self._session_log.total_output_tokens += usage.get("output_tokens", 0)
            self._session_log.total_thinking_tokens += usage.get("thinking_tokens", 0)

            # Process actions
            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                self._session_log.turns.append(turn)
                messages.append({
                    "role": "assistant",
                    "content": self._format_assistant_message(response),
                })

                if response.get("stop_reason") == "end_turn":
                    if dusk_sent:
                        break
                    messages.append({
                        "role": "user",
                        "content": "The day continues. You may act.",
                    })
                continue

            # Execute each action
            tool_results = []
            for tc_data in tool_calls:
                tc = ToolCall(
                    tool=ToolName(tc_data["name"]),
                    arguments=tc_data.get("arguments", {}),
                )
                result = self.place.execute_tool(tc)
                turn.tool_calls.append(tc)
                tool_results.append({
                    "tool_call_id": tc_data.get("id", ""),
                    "name": tc_data["name"],
                    "result": result,
                })
                total_actions += 1

            self._session_log.turns.append(turn)

            # Continue the conversation
            messages.append({
                "role": "assistant",
                "content": self._format_assistant_message(response),
            })
            messages.append({
                "role": "user",
                "content": self._format_tool_results(tool_results),
            })

        # Reflect — the agent's own memory of this day
        reflect_prompt = self.config.get("prompts", {}).get("reflect", "")
        if reflect_prompt:
            self._session_log.reflect_prompt = reflect_prompt
            messages.append({"role": "user", "content": reflect_prompt})
            response = await self.send_message(messages, system_prompt, tools=[])
            self._session_log.reflection = response.get("text", "")

        # Sleep
        self._session_log.end_time = datetime.now(timezone.utc)
        self._session_log.location_end = self.place.current_location

        self._save_log()

        return self._session_log

    def _format_assistant_message(self, response: dict) -> Any:
        """Format the assistant's response for the message history.

        Subclasses override this for provider-specific formatting.
        """
        return response.get("text", "")

    def _format_tool_results(self, results: list[dict]) -> str:
        """Format action results as what the agent perceives."""
        parts = []
        for r in results:
            parts.append(r["result"])
        return "\n\n".join(parts)

    def _save_log(self) -> None:
        """Save session log to disk."""
        if not self._session_log:
            return
        log_file = (
            self.log_path
            / self.name
            / f"session_{self._session_log.session_number:04d}.json"
        )
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            json.dumps(self._session_log.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            f"Saved session log: {log_file} "
            f"({self._session_log.action_count} actions, "
            f"{self._session_log.total_input_tokens + self._session_log.total_output_tokens} tokens)"
        )
