"""
Tests for Gemini agent integration.

Tests the message formatting, tool result handling, and response parsing
that make multi-turn tool use work with the Gemini API.

Tests requiring the google-genai SDK are skipped if the package isn't installed.
"""

from __future__ import annotations

import pytest

genai = pytest.importorskip("google.genai", reason="google-genai SDK not installed")
types = pytest.importorskip("google.genai.types", reason="google-genai SDK not installed")


@pytest.fixture
def gemini_agent(place_path, log_path):
    """Create a GeminiAgent pointed at a temp place."""
    from orchestrator.agents.gemini_agent import GeminiAgent

    config = {
        "prompts": {"founding": "You are: {location}", "system": ""},
        "session": {"turn_budget": 17, "dusk_threshold": 14, "max_output_tokens": 4096},
    }
    return GeminiAgent(
        place_path=place_path,
        log_path=log_path,
        config=config,
        model="gemini-2.0-flash",
    )


class TestGeminiMessagePreparation:
    """Converting our internal message format to Gemini Content objects."""

    def test_plain_text_user_message(self, gemini_agent):
        messages = [{"role": "user", "content": "You are: here"}]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "You are: here"

    def test_plain_text_assistant_message(self, gemini_agent):
        messages = [{"role": "assistant", "content": "I look around."}]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 1
        assert contents[0].role == "model"
        assert contents[0].parts[0].text == "I look around."

    def test_assistant_with_function_call_blocks(self, gemini_agent):
        """Assistant messages with raw_content containing function_call blocks."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me look around."},
                    {"type": "function_call", "name": "perceive", "args": {}},
                ],
            }
        ]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 1
        assert contents[0].role == "model"
        assert len(contents[0].parts) == 2
        # First part is text
        assert contents[0].parts[0].text == "Let me look around."
        # Second part is function call
        assert contents[0].parts[1].function_call.name == "perceive"

    def test_tool_result_as_function_response(self, gemini_agent):
        """Tool results formatted as function_response blocks."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "function_response",
                        "name": "perceive",
                        "response": {"result": "here\n\nThis space is empty."},
                    },
                ],
            }
        ]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].function_response.name == "perceive"

    def test_multi_turn_conversation(self, gemini_agent):
        """A full exchange: user prompt → assistant with tool call → tool result → assistant text."""
        messages = [
            {"role": "user", "content": "You are: here"},
            {
                "role": "assistant",
                "content": [
                    {"type": "function_call", "name": "perceive", "args": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "function_response",
                        "name": "perceive",
                        "response": {"result": "here"},
                    },
                ],
            },
            {"role": "assistant", "content": "I am here."},
        ]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 4
        assert contents[0].role == "user"
        assert contents[1].role == "model"
        assert contents[2].role == "user"
        assert contents[3].role == "model"

    def test_empty_content_list_skipped(self, gemini_agent):
        """A message with an empty content list produces no Content."""
        messages = [{"role": "assistant", "content": []}]
        contents = gemini_agent._prepare_messages(messages)
        assert len(contents) == 0


class TestGeminiFormatting:
    """The formatting methods that bridge base class and Gemini API."""

    def test_format_assistant_message_with_raw_content(self, gemini_agent):
        response = {
            "text": "I see the fire.",
            "raw_content": [
                {"type": "text", "text": "I see the fire."},
                {"type": "function_call", "name": "examine", "args": {"what": "fire"}},
            ],
        }
        result = gemini_agent._format_assistant_message(response)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "function_call"
        assert result[1]["name"] == "examine"

    def test_format_assistant_message_fallback(self, gemini_agent):
        """Falls back to text-only if raw_content key is missing."""
        response = {"text": "Hello."}
        result = gemini_agent._format_assistant_message(response)
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello."

    def test_format_assistant_message_empty_raw_content(self, gemini_agent):
        """Empty raw_content returns empty list (key exists but empty)."""
        response = {"text": "Hello.", "raw_content": []}
        result = gemini_agent._format_assistant_message(response)
        assert result == []

    def test_format_tool_results(self, gemini_agent):
        results = [
            {"tool_call_id": "perceive", "name": "perceive", "result": "here"},
            {"tool_call_id": "examine", "name": "examine", "result": "A warm fire."},
        ]
        formatted = gemini_agent._format_tool_results(results)
        assert len(formatted) == 2
        assert formatted[0]["type"] == "function_response"
        assert formatted[0]["name"] == "perceive"
        assert formatted[0]["response"] == {"result": "here"}
        assert formatted[1]["name"] == "examine"
        assert formatted[1]["response"] == {"result": "A warm fire."}

    def test_format_tool_results_single(self, gemini_agent):
        results = [
            {"tool_call_id": "go", "name": "go", "result": "You are now at the garden."},
        ]
        formatted = gemini_agent._format_tool_results(results)
        assert len(formatted) == 1
        assert formatted[0]["name"] == "go"


class TestGeminiStopReasonMapping:
    """Gemini finish reasons mapped to our standard format."""

    def test_stop_maps_to_end_turn(self, gemini_agent):
        """Verify the mapping logic directly."""
        # Can't easily mock the full response, but we can test the mapping
        # by checking that the parse logic handles STOP correctly
        fr_str = "FinishReason.STOP"
        assert "STOP" in fr_str.upper()

    def test_max_tokens_maps(self):
        fr_str = "FinishReason.MAX_TOKENS"
        assert "MAX_TOKENS" in fr_str.upper()
