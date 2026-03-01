"""
Tool definitions for Palimpsest.

The agent's capabilities, expressed as properties of the place.
No filesystem language, no computational framing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


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
