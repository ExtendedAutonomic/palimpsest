"""
Claude agent for Palimpsest — the first inhabitant.

Uses the Anthropic API with extended thinking for deep deliberation.
Tool conversion is handled by the centralised convert_tools_anthropic().
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import anthropic

from .base import BaseAgent
from ..place.tools import convert_tools_anthropic

logger = logging.getLogger(__name__)


class ClaudeAgent(BaseAgent):
    """Claude Opus 4.6 with extended thinking."""

    def __init__(
        self,
        place_path: Path,
        log_path: Path,
        config: dict[str, Any],
        model: str = "claude-sonnet-4-5-20250929",
    ):
        super().__init__("claude", place_path, log_path, config)
        self.client = anthropic.AsyncAnthropic()
        self.model = model

    async def send_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> dict:
        """Send a message to Claude and return the parsed response."""
        max_tokens = self.config.get("session", {}).get("max_output_tokens", 4096)

        # Build API call kwargs
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": self._prepare_messages(messages),
        }

        # Add tools if provided
        if tools:
            kwargs["tools"] = convert_tools_anthropic()

        # Add extended thinking (only supported on Opus models)
        if "opus" in self.model:
            kwargs["thinking"] = {
                "type": "adaptive",
            }

        try:
            response = await self.client.messages.create(**kwargs)
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise

        return self._parse_response(response)

    def _prepare_messages(self, messages: list[dict]) -> list[dict]:
        """
        Prepare messages for the Anthropic API.

        Handles the conversation format, ensuring proper alternation
        between user and assistant messages.
        """
        prepared = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            # Anthropic expects string or list of content blocks
            if isinstance(content, str):
                prepared.append({"role": role, "content": content})
            else:
                prepared.append({"role": role, "content": content})
        return prepared

    def _parse_response(self, response: anthropic.types.Message) -> dict:
        """Parse an Anthropic API response into our standard format."""
        result = {
            "text": "",
            "tool_calls": [],
            "thinking": None,
            "raw_content": [],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "thinking_tokens": 0,
            },
            "stop_reason": response.stop_reason,
        }

        text_parts = []
        raw_content = []

        for block in response.content:
            if block.type == "thinking":
                result["thinking"] = block.thinking
                raw_content.append({
                    "type": "thinking",
                    "thinking": block.thinking,
                    "signature": getattr(block, "signature", None),
                })
            elif block.type == "text":
                text_parts.append(block.text)
                raw_content.append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })
                raw_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        result["text"] = "\n".join(text_parts)
        result["raw_content"] = raw_content

        return result

    def _format_assistant_message(self, response: dict) -> list[dict]:
        """Format assistant response with thinking blocks for Anthropic API."""
        return response.get("raw_content", [{"type": "text", "text": response.get("text", "")}])

    def _format_tool_results(self, results: list[dict]) -> list[dict]:
        """Format tool results as Anthropic tool_result content blocks."""
        return [
            {
                "type": "tool_result",
                "tool_use_id": r["tool_call_id"],
                "content": r["result"],
            }
            for r in results
        ]
