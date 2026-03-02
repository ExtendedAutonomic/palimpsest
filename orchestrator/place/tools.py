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
    # Hidden tools — not in initial tool definitions, unlocked through play
    TAKE = "take"
    DROP = "drop"


# Canonical tool definitions — provider-agnostic.
# Each tool has a name, description, and parameters dict.
# Parameters use "optional": True to mark non-required fields.
AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "perceive",
        "parameters": {},
    },
    {
        "name": "go",
        "parameters": {
            "where": {
                "type": "string",
            }
        },
    },
    {
        "name": "venture",
        "parameters": {
            "name": {
                "type": "string",
            },
            "description": {
                "type": "string",
            }
        },
    },
    {
        "name": "examine",
        "parameters": {
            "what": {
                "type": "string",
            }
        },
    },
    {
        "name": "create",
        "parameters": {
            "name": {
                "type": "string",
            },
            "description": {
                "type": "string",
            },
        },
    },
    {
        "name": "alter",
        "parameters": {
            "what": {
                "type": "string",
            },
            "description": {
                "type": "string",
                "optional": True,
            },
            "name": {
                "type": "string",
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
    Description fields are only included when present in the source.
    """
    tools = tools or AGENT_TOOLS
    converted = []
    for tool in tools:
        properties = {}
        required = []
        for param_name, param_def in tool.get("parameters", {}).items():
            prop = {"type": param_def.get("type", "string")}
            if "description" in param_def:
                prop["description"] = param_def["description"]
            properties[param_name] = prop
            if not param_def.get("optional", False):
                required.append(param_name)

        entry = {
            "name": tool["name"],
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
        if "description" in tool:
            entry["description"] = tool["description"]
        converted.append(entry)
    return converted


def convert_tools_openai(tools: list[dict] | None = None) -> list[dict]:
    """Convert tool definitions to OpenAI-compatible function calling format.

    Used by DeepSeek and any other OpenAI-compatible provider.
    Respects the 'optional' flag on parameters.
    Description fields are only included when present in the source.
    """
    tools = tools or AGENT_TOOLS
    converted = []
    for tool in tools:
        properties = {}
        required = []
        for param_name, param_def in tool.get("parameters", {}).items():
            prop = {"type": param_def.get("type", "string")}
            if "description" in param_def:
                prop["description"] = param_def["description"]
            properties[param_name] = prop
            if not param_def.get("optional", False):
                required.append(param_name)

        func = {
            "name": tool["name"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            } if properties else {"type": "object", "properties": {}},
        }
        if "description" in tool:
            func["description"] = tool["description"]
        converted.append({"type": "function", "function": func})
    return converted


def convert_tools_gemini(tools: list[dict] | None = None) -> list:
    """Convert tool definitions to Gemini's format.

    Uses the google-genai SDK types. Respects 'optional' flag.
    Description fields are only included when present in the source.
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
            schema_kwargs = {"type": types.Type.STRING}
            if "description" in param_def:
                schema_kwargs["description"] = param_def["description"]
            properties[param_name] = types.Schema(**schema_kwargs)
            if not param_def.get("optional", False):
                required.append(param_name)

        fd_kwargs = {"name": tool["name"]}
        if "description" in tool:
            fd_kwargs["description"] = tool["description"]
        if properties:
            fd_kwargs["parameters"] = types.Schema(
                type=types.Type.OBJECT,
                properties=properties,
                required=required,
            )
        fd = types.FunctionDeclaration(**fd_kwargs)
        function_declarations.append(fd)

    return [types.Tool(function_declarations=function_declarations)]


# Hidden tool definitions — not sent to the API initially.
# Unlocked when the agent demonstrates need (e.g. tries to examine
# something that exists in the world but not in its current space).
HIDDEN_TOOLS: dict[str, dict[str, Any]] = {
    "take": {
        "name": "take",
        "parameters": {
            "what": {
                "type": "string",
            }
        },
    },
    "drop": {
        "name": "drop",
        "parameters": {
            "what": {
                "type": "string",
            }
        },
    },
}


@dataclass
class ToolCall:
    """A single action taken by the agent."""
    tool: ToolName
    arguments: dict[str, str]
    result: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
