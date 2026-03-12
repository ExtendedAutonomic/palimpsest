"""
Tests for Claude agent message formatting.

Ensures thinking blocks (with signatures) and tool use blocks survive
the _prepare_messages round trip. Claude's implementation passes content
through largely unchanged, but these tests guard against regressions.
"""

from __future__ import annotations

import pytest

from orchestrator.agents.claude_agent import ClaudeAgent


@pytest.fixture
def claude_agent(place_path, log_path):
    """Create a ClaudeAgent pointed at a temp place."""
    config = {
        "prompts": {"founding": "You are: {location}"},
    }
    agent_config = {
        "extended_thinking": True,
        "session": {"max_output_tokens": 4096},
    }
    return ClaudeAgent(
        place_path=place_path,
        log_path=log_path,
        config=config,
        agent_config=agent_config,
        model="claude-opus-4-6",
    )


class TestClaudeMessagePreparation:
    """Claude's _prepare_messages preserves all content block types."""

    def test_first_message_gets_cache_control(self, claude_agent):
        messages = [{"role": "user", "content": "You are: here"}]
        prepared = claude_agent._prepare_messages(messages)
        assert prepared[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert prepared[0]["content"][0]["text"] == "You are: here"

    def test_thinking_with_signature_preserved(self, claude_agent):
        """Thinking blocks with signatures must pass through unchanged."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "I should perceive.", "signature": "abc123"},
                    {"type": "text", "text": "Let me look."},
                ],
            }
        ]
        prepared = claude_agent._prepare_messages(messages)
        content = prepared[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "thinking"
        assert content[0]["thinking"] == "I should perceive."
        assert content[0]["signature"] == "abc123"
        assert content[1]["type"] == "text"

    def test_tool_use_and_result_preserved(self, claude_agent):
        """tool_use and tool_result blocks pass through unchanged."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tc_1", "name": "perceive", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tc_1", "content": "here"},
                ],
            },
        ]
        prepared = claude_agent._prepare_messages(messages)
        assert prepared[0]["content"][0]["type"] == "tool_use"
        assert prepared[0]["content"][0]["name"] == "perceive"
        assert prepared[1]["content"][0]["type"] == "tool_result"

    def test_no_block_types_silently_dropped(self, claude_agent):
        """Every block type produced by _parse_response survives _prepare_messages."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "planning...", "signature": "sig"},
                    {"type": "text", "text": "speaking..."},
                    {"type": "tool_use", "id": "tc_1", "name": "perceive", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tc_1", "content": "here"},
                ],
            },
        ]
        prepared = claude_agent._prepare_messages(messages)
        # Assistant: 3 blocks in, 3 blocks out
        assert len(prepared[0]["content"]) == 3, (
            f"Expected 3 blocks (thinking + text + tool_use), "
            f"got {len(prepared[0]['content'])}. A block type is being silently dropped."
        )
        # User: 1 block in, 1 block out
        assert len(prepared[1]["content"]) == 1
