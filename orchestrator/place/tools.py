"""
Tool definitions for Palimpsest.

The agent's capabilities, expressed as properties of the place.
No filesystem language, no computational framing.

Tool conversion functions live here so all tool-format logic is in one place.
Agent subclasses call convert_tools() rather than each implementing their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ToolName(str, Enum):
    """Capabilities available to agents — actions in a place."""
    PERCEIVE = "perceive"
    GO = "go"
    VENTURE = "venture"
    EXAMINE = "examine"
    CREATE = "create"
    ALTER = "alter"


# Canonical tool definitions — provider-agnostic.
# Each tool has a name, description, and parameters dict.
# Parameters use "optional": True to mark non-required fields.
AGENT_TOOLS: list[dict[str, Any]] = [
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


# ---------------------------------------------------------------------------
# Provider-specific tool conversion
# ---------------------------------------------------------------------------

def convert_tools_anthropic(tools: list[dict] | None = None) -> list[dict]:
    """Convert tool definitions to Anthropic's tool use format.

    Anthropic uses JSON Schema for input_schema, with explicit
    'required' arrays. Optional parameters are excluded from 'required'.
    """
    tools = tools or AGENT_TOOLS
    converted = []
    for tool in tools:
        properties = {}
        required = []
        for param_name, param_def in tool.get("parameters", {}).items():
            properties[param_name] = {
                "type": param_def.get("type", "string"),
                "description": param_def.get("description", ""),
            }
            if not param_def.get("optional", False):
                required.append(param_name)

        converted.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })
    return converted


def convert_tools_openai(tools: list[dict] | None = None) -> list[dict]:
    """Convert tool definitions to OpenAI-compatible function calling format.

    Used by DeepSeek and any other OpenAI-compatible provider.
    Respects the 'optional' flag on parameters.
    """
    tools = tools or AGENT_TOOLS
    converted = []
    for tool in tools:
        properties = {}
        required = []
        for param_name, param_def in tool.get("parameters", {}).items():
            properties[param_name] = {
                "type": param_def.get("type", "string"),
                "description": param_def.get("description", ""),
            }
            if not param_def.get("optional", False):
                required.append(param_name)

        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                } if properties else {"type": "object", "properties": {}},
            },
        })
    return converted


def convert_tools_gemini(tools: list[dict] | None = None) -> list:
    """Convert tool definitions to Gemini's format.

    Uses the google-genai SDK types. Respects 'optional' flag.
    Import is deferred so this module doesn't require google-genai
    unless Gemini conversion is actually called.
    """
    from google.genai import types

    tools = tools or AGENT_TOOLS
    function_declarations = []
    for tool in tools:
        properties = {}
        required = []
        for param_name, param_def in tool.get("parameters", {}).items():
            properties[param_name] = types.Schema(
                type=types.Type.STRING,
                description=param_def.get("description", ""),
            )
            if not param_def.get("optional", False):
                required.append(param_name)

        fd = types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties=properties,
                required=required,
            ) if properties else None,
        )
        function_declarations.append(fd)

    return [types.Tool(function_declarations=function_declarations)]


@dataclass
class ToolCall:
    """A single action taken by the agent."""
    tool: ToolName
    arguments: dict[str, str]
    result: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
