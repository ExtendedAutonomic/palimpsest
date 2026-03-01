"""
Tests for tool definitions and provider-specific conversion.

Verifies that the canonical tool definitions convert correctly
to each provider's format, including proper handling of optional
parameters.
"""

from __future__ import annotations

from orchestrator.place.tools import (
    AGENT_TOOLS,
    convert_tools_anthropic,
    convert_tools_openai,
)


class TestCanonicalTools:
    """The canonical tool definitions are well-formed."""

    def test_six_tools_defined(self):
        assert len(AGENT_TOOLS) == 6

    def test_tool_names(self):
        names = [t["name"] for t in AGENT_TOOLS]
        assert names == ["perceive", "go", "venture", "examine", "create", "alter"]

    def test_all_tools_have_descriptions(self):
        for tool in AGENT_TOOLS:
            assert "description" in tool
            assert len(tool["description"]) > 0

    def test_perceive_has_no_parameters(self):
        perceive = AGENT_TOOLS[0]
        assert perceive["parameters"] == {}

    def test_alter_has_optional_params(self):
        alter = AGENT_TOOLS[5]
        assert alter["parameters"]["description"].get("optional") is True
        assert alter["parameters"]["name"].get("optional") is True
        assert alter["parameters"]["what"].get("optional") is not True


class TestAnthropicConversion:
    """Anthropic tool format — JSON Schema with input_schema."""

    def test_converts_all_tools(self):
        converted = convert_tools_anthropic()
        assert len(converted) == 6

    def test_has_input_schema(self):
        converted = convert_tools_anthropic()
        for tool in converted:
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_perceive_has_empty_properties(self):
        converted = convert_tools_anthropic()
        perceive = converted[0]
        assert perceive["input_schema"]["properties"] == {}
        assert perceive["input_schema"]["required"] == []

    def test_alter_optional_params_not_required(self):
        """Optional params should NOT appear in the required array."""
        converted = convert_tools_anthropic()
        alter = converted[5]
        required = alter["input_schema"]["required"]
        assert "what" in required
        assert "description" not in required
        assert "name" not in required

    def test_go_required_param(self):
        converted = convert_tools_anthropic()
        go = converted[1]
        assert "where" in go["input_schema"]["required"]


class TestOpenAIConversion:
    """OpenAI-compatible format — function calling (used by DeepSeek)."""

    def test_converts_all_tools(self):
        converted = convert_tools_openai()
        assert len(converted) == 6

    def test_has_function_wrapper(self):
        converted = convert_tools_openai()
        for tool in converted:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]

    def test_alter_optional_params_not_required(self):
        """The optional flag fix — DeepSeek was previously requiring all params."""
        converted = convert_tools_openai()
        alter = converted[5]
        required = alter["function"]["parameters"]["required"]
        assert "what" in required
        assert "description" not in required
        assert "name" not in required

    def test_perceive_has_empty_properties(self):
        converted = convert_tools_openai()
        perceive = converted[0]
        assert perceive["function"]["parameters"]["properties"] == {}


class TestCustomToolConversion:
    """Conversion with custom tool lists (not just AGENT_TOOLS)."""

    def test_anthropic_custom_tools(self):
        custom = [
            {
                "name": "listen",
                "description": "Listen carefully.",
                "parameters": {
                    "direction": {"type": "string", "description": "Where to listen."},
                },
            }
        ]
        converted = convert_tools_anthropic(custom)
        assert len(converted) == 1
        assert converted[0]["name"] == "listen"
        assert "direction" in converted[0]["input_schema"]["properties"]

    def test_openai_custom_tools(self):
        custom = [
            {
                "name": "listen",
                "description": "Listen carefully.",
                "parameters": {},
            }
        ]
        converted = convert_tools_openai(custom)
        assert len(converted) == 1
        assert converted[0]["function"]["name"] == "listen"
