"""
Base agent class for Palimpsest.

Each agent experiences the place as a spatial environment: it has a location,
can see only its immediate surroundings, and must move to explore.
The agent interacts via tools that describe capabilities of the place itself —
no filesystem language, no computational framing.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
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
    BUILD = "build"


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
            "Go somewhere. You may enter any space you can perceive from "
            "where you are, or you may go back the way you came."
        ),
        "parameters": {
            "where": {
                "type": "string",
                "description": (
                    "The name of a space to enter, "
                    'or "back" to return the way you came.'
                ),
            }
        },
    },
    {
        "name": "venture",
        "description": (
            "Go somewhere new. You move beyond where you are into the unknown. "
            "You must name where you find yourself. You will be there."
        ),
        "parameters": {
            "name": {
                "type": "string",
                "description": "What you call this new place.",
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
            "The original is replaced. What was there before is lost."
        ),
        "parameters": {
            "what": {
                "type": "string",
                "description": "The name of the thing to change.",
            },
            "description": {
                "type": "string",
                "description": "What it becomes.",
            },
        },
    },
    {
        "name": "build",
        "description": (
            "Make a new space here. It exists alongside you — "
            "you remain where you are. You may go there later."
        ),
        "parameters": {
            "name": {
                "type": "string",
                "description": "What to call this space.",
            }
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
    turns: list[Turn] = field(default_factory=list)
    reflection: str | None = None
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
            "action_count": self.action_count,
            "reflection": self.reflection,
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


class PlaceInterface:
    """
    The place as experienced by an agent — spatial, local, persistent.

    Translates agent actions into filesystem operations while enforcing
    perceptual locality: agents can only perceive their immediate surroundings.

    All responses are written in the language of the place, never in
    filesystem terminology.
    """

    def __init__(self, place_path: Path):
        self.place_path = place_path.resolve()
        self._current_location = PurePosixPath("here")

    @property
    def current_location(self) -> str:
        return str(self._current_location)

    @current_location.setter
    def current_location(self, value: str) -> None:
        self._current_location = PurePosixPath(value)

    def _resolve(self, relative: str = "") -> Path:
        """Resolve a path relative to current location within the place."""
        if relative:
            target = self._current_location / relative
        else:
            target = self._current_location
        resolved = (self.place_path / target).resolve()
        if not str(resolved).startswith(str(self.place_path)):
            raise PermissionError("You cannot go there.")
        return resolved

    def _describe_contents(self, path: Path) -> str:
        """Describe what is present in a location."""
        if not path.exists():
            return "There is nothing here."

        items = sorted(path.iterdir())
        items = [i for i in items if not i.name.startswith(".")]

        if not items:
            return "This space is empty."

        parts = []
        spaces = [i for i in items if i.is_dir()]
        things = [i for i in items if i.is_file()]

        if spaces and things:
            space_names = ", ".join(f"[{s.name}]" for s in spaces)
            thing_names = ", ".join(t.name for t in things)
            parts.append(f"There are spaces here: {space_names}")
            parts.append(f"There are things here: {thing_names}")
        elif spaces:
            space_names = ", ".join(f"[{s.name}]" for s in spaces)
            parts.append(f"There are spaces here: {space_names}")
        elif things:
            thing_names = ", ".join(t.name for t in things)
            parts.append(f"There are things here: {thing_names}")

        return "\n".join(parts)

    def perceive(self) -> str:
        """Take in surroundings."""
        path = self._resolve()
        return self._describe_contents(path)

    def go(self, where: str) -> str:
        """Move to another space."""
        if where == "back":
            if self._current_location == PurePosixPath("."):
                return "There is nowhere further back to go. You are at the edge of the place."
            self._current_location = self._current_location.parent
            contents = self._describe_contents(self._resolve())
            location_name = self.current_location if self.current_location != "." else "the outermost space"
            return f"You go back. You are now in: {location_name}\n\n{contents}"

        target = self._resolve(where)
        if not target.exists():
            return f"There is no space called \"{where}\" here."
        if not target.is_dir():
            return f"\"{where}\" is not a space. It is a thing. You could examine it."

        self._current_location = self._current_location / where
        contents = self._describe_contents(self._resolve())
        return f"You go into {where}.\n\n{contents}"

    def venture(self, name: str) -> str:
        """Go somewhere new — create a space and move into it."""
        target = self._resolve(name)
        if target.exists():
            return f"A place called \"{name}\" already exists here. You could go there."
        try:
            target.mkdir(parents=True, exist_ok=True)
            self._current_location = self._current_location / name
            return f"You venture into {name}. You are there now.\n\nThis space is empty."
        except Exception as e:
            return "You cannot go that way."

    def examine(self, what: str) -> str:
        """Look closely at something."""
        target = self._resolve(what)
        if not target.exists():
            return f"There is nothing called \"{what}\" here."
        if target.is_dir():
            return f"\"{what}\" is a space, not a thing. You could go there."
        try:
            content = target.read_text(encoding="utf-8")
            return content if content.strip() else "It is blank. There is nothing to perceive."
        except Exception as e:
            return "You cannot make sense of it."

    def create(self, name: str, description: str) -> str:
        """Create something in the current space."""
        target = self._resolve(name)
        if target.exists():
            return (
                f"Something called \"{name}\" already exists here. "
                "You could alter it, but you cannot create over it."
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(description, encoding="utf-8")
            return f"You create {name}. It is here now, and it will remain."
        except Exception as e:
            return "You cannot create that here."

    def alter(self, what: str, description: str) -> str:
        """Change something that exists."""
        target = self._resolve(what)
        if not target.exists():
            return f"There is nothing called \"{what}\" here to alter."
        if target.is_dir():
            return f"\"{what}\" is a space. You cannot alter a space this way."
        try:
            target.write_text(description, encoding="utf-8")
            return f"You alter {what}. It is different now. What was there before is gone."
        except Exception as e:
            return "You cannot alter that."

    def build(self, name: str) -> str:
        """Make a new space here — stay where you are."""
        target = self._resolve(name)
        if target.exists():
            return f"A space called \"{name}\" is already here."
        try:
            target.mkdir(parents=True, exist_ok=True)
            return f"A new space takes shape: {name}. It is empty."
        except Exception as e:
            return "You cannot build a space here."

    def execute_tool(self, tool_call: ToolCall) -> str:
        """Execute an action and return what the agent perceives."""
        handlers = {
            ToolName.PERCEIVE: lambda args: self.perceive(),
            ToolName.GO: lambda args: self.go(args["where"]),
            ToolName.VENTURE: lambda args: self.venture(args["name"]),
            ToolName.EXAMINE: lambda args: self.examine(args["what"]),
            ToolName.CREATE: lambda args: self.create(args["name"], args["description"]),
            ToolName.ALTER: lambda args: self.alter(args["what"], args["description"]),
            ToolName.BUILD: lambda args: self.build(args["name"]),
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
        self.place = PlaceInterface(place_path)
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

        # Set starting location
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
                memory=memory or "(You remember nothing specific.)",
                diff=diff or "(Nothing seems to have changed.)",
                location=self.place.current_location,
                surroundings=surroundings,
            )

        system_prompt = self.config.get("prompts", {}).get("system", "")
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
                messages.append({"role": "assistant", "content": response["text"]})

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
                "content": response.get("raw_content", response["text"]),
            })
            messages.append({
                "role": "user",
                "content": self._format_tool_results(tool_results),
            })

        # Reflect — the agent's own memory of this day
        reflect_prompt = self.config.get("prompts", {}).get("reflect", "")
        if reflect_prompt:
            messages.append({"role": "user", "content": reflect_prompt})
            response = await self.send_message(messages, system_prompt, tools=[])
            self._session_log.reflection = response.get("text", "")

        # Sleep
        self._session_log.end_time = datetime.now(timezone.utc)
        self._session_log.location_end = self.place.current_location

        self._save_log()

        return self._session_log

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
