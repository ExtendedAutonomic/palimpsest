"""
Tests for tool definitions and provider-specific conversion.

Verifies that the canonical tool definitions convert correctly
to each provider's format, including proper handling of optional
parameters.
"""

from __future__ import annotations

import pytest

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

    def test_tools_have_no_descriptions(self):
        """Minimal experiment: tools have no descriptions."""
        for tool in AGENT_TOOLS:
            assert "description" not in tool

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
            # Minimal: no descriptions
            assert "description" not in tool["function"]

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


class TestGeminiConversion:
    """Gemini tool format — google.genai types."""

    @pytest.fixture(autouse=True)
    def _skip_without_genai(self):
        pytest.importorskip("google.genai", reason="google-genai SDK not installed")

    def test_converts_all_tools(self):
        from orchestrator.place.tools import convert_tools_gemini
        converted = convert_tools_gemini()
        # Returns a list containing one Tool object with function_declarations
        assert len(converted) == 1
        declarations = converted[0].function_declarations
        assert len(declarations) == 6

    def test_tool_names_match(self):
        from orchestrator.place.tools import convert_tools_gemini
        converted = convert_tools_gemini()
        names = [fd.name for fd in converted[0].function_declarations]
        assert names == ["perceive", "go", "venture", "examine", "create", "alter"]

    def test_perceive_has_no_parameters(self):
        from orchestrator.place.tools import convert_tools_gemini
        converted = convert_tools_gemini()
        perceive = converted[0].function_declarations[0]
        assert perceive.parameters is None

    def test_tools_have_no_descriptions(self):
        """Minimal experiment: tool descriptions are omitted."""
        from orchestrator.place.tools import convert_tools_gemini
        converted = convert_tools_gemini()
        for fd in converted[0].function_declarations:
            assert fd.description is None

    def test_alter_optional_params(self):
        """Optional params should not appear in required."""
        from orchestrator.place.tools import convert_tools_gemini
        converted = convert_tools_gemini()
        alter = converted[0].function_declarations[5]
        assert "what" in alter.parameters.required
        assert "description" not in alter.parameters.required
        assert "name" not in alter.parameters.required

    def test_custom_tools(self):
        from orchestrator.place.tools import convert_tools_gemini
        custom = [
            {
                "name": "listen",
                "description": "Listen carefully.",
                "parameters": {
                    "direction": {"type": "string"},
                },
            }
        ]
        converted = convert_tools_gemini(custom)
        assert len(converted) == 1
        declarations = converted[0].function_declarations
        assert len(declarations) == 1
        assert declarations[0].name == "listen"
        assert declarations[0].description == "Listen carefully."
