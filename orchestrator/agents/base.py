"""
Base agent class for Palimpsest.

Each agent experiences the place as a spatial environment: it has a location,
can see only its immediate surroundings, and must move to explore.

v2: Linked notes architecture. Everything is a markdown note. Spaces contain
wiki links to other spaces and things. The Obsidian graph becomes the map.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..place import PlaceInterface, ToolName, ToolCall, AGENT_TOOLS

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """One exchange in a session: agent response + any actions taken."""
    agent_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None  # Extended thinking (Claude only)
    nudge: str | None = None  # Injected user message after this turn (e.g. "...")
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
    dusk_action: int | None = None  # Action count when dusk was sent
    reflect_prompt: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model: str | None = None
    cost: float | None = None

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
            "dusk_action": self.dusk_action,
            "reflect_prompt": self.reflect_prompt,
            "model": self.model,
            "cost": self.cost,
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
            },
            "turns": [
                {
                    "agent_text": t.agent_text,
                    "thinking": t.thinking,
                    "nudge": t.nudge,
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
        start_location: str | None = None,
    ) -> SessionLog:
        """
        Run a complete agent session.

        The arc of a day: wake → act → dusk → reflect → sleep.
        """
        now = datetime.now(timezone.utc)
        action_budget = self.config.get("session", {}).get("action_budget", 25)
        dusk_threshold = self.config.get("session", {}).get("dusk_threshold", 22)
        max_turns = action_budget  # Each turn has equal weight

        # Set starting location and session context
        self.place._session_number = session_number
        if start_location:
            self.place.current_location = start_location
        else:
            # Session 1 — setter never fires, so set occupant manually
            self.place._set_occupant(self.place.current_location)

        self._session_log = SessionLog(
            agent_name=self.name,
            session_number=session_number,
            phase=phase,
            start_time=now,
            location_start=self.place.current_location,
            model=getattr(self, "model", None),
        )

        # Build the opening message
        if session_number == 1:
            opening = self.config.get("prompts", {}).get("founding", "You are here.")
        else:
            identity_template = self.config.get("prompts", {}).get("identity", "")
            opening = identity_template.format(
                memory=memory or "",
                location=self.place.current_location,
            )

        system_prompt = self.config.get("prompts", {}).get("system", "")
        self._session_log.opening_prompt = opening
        self._session_log.system_prompt = system_prompt
        messages = [{"role": "user", "content": opening}]
        tools = self.get_tool_definitions()

        # Add any previously unlocked hidden tools
        if self.place.permanently_unlocked_tools:
            from ..place.tools import HIDDEN_TOOLS
            for tool_name in self.place.permanently_unlocked_tools:
                if tool_name in HIDDEN_TOOLS:
                    tool_def = HIDDEN_TOOLS[tool_name]
                    if tool_def not in tools:
                        tools.append(tool_def)
                        logger.info(f"Loaded unlocked tool: {tool_name}")

        total_actions = 0
        dusk_sent = False
        for turn_idx in range(max_turns):
            # Dusk approaches — counted by turns, not actions
            if turn_idx >= dusk_threshold and not dusk_sent:
                dusk_prompt = self.config.get("prompts", {}).get("dusk", "")
                messages.append({"role": "user", "content": dusk_prompt})
                self._session_log.dusk_prompt = dusk_prompt
                self._session_log.dusk_action = turn_idx
                dusk_sent = True

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

            # Process actions
            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                if response.get("stop_reason") == "end_turn":
                    # The agent spoke without acting — nudge it.
                    turn.nudge = "..."
                    messages.append({
                        "role": "assistant",
                        "content": self._format_assistant_message(response),
                    })
                    messages.append({
                        "role": "user",
                        "content": "...",
                    })
                else:
                    messages.append({
                        "role": "assistant",
                        "content": self._format_assistant_message(response),
                    })
                self._session_log.turns.append(turn)
                continue

            # Execute each action
            tool_results = []
            for tc_data in tool_calls:
                try:
                    tc = ToolCall(
                        tool=ToolName(tc_data["name"]),
                        arguments=tc_data.get("arguments", {}),
                    )
                    result = self.place.execute_tool(tc)
                    turn.tool_calls.append(tc)
                except (ValueError, KeyError) as e:
                    # Model returned a garbled or unknown tool name
                    logger.warning(f"Invalid tool call: {tc_data.get('name', '?')} — {e}")
                    result = "You do not know how to do that."
                tool_results.append({
                    "tool_call_id": tc_data.get("id", ""),
                    "name": tc_data.get("name", "unknown"),
                    "result": result,
                })
                total_actions += 1

            self._session_log.turns.append(turn)

            # Check for newly unlocked tools (e.g. examine triggered take)
            if self.place._unlocked_tools:
                from ..place.tools import HIDDEN_TOOLS
                for tool_name in list(self.place._unlocked_tools):
                    if tool_name in HIDDEN_TOOLS:
                        tool_def = HIDDEN_TOOLS[tool_name]
                        if tool_def not in tools:
                            tools.append(tool_def)
                            logger.info(f"Tool unlocked: {tool_name}")
                self.place._unlocked_tools.clear()

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
