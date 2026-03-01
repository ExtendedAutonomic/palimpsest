"""
DeepSeek agent for Palimpsest — the Third.

Uses the OpenAI-compatible API. Enters during Phase 4.
The wildcard — terse, sober, potentially drawing on different philosophical traditions.
Tool conversion is handled by the centralised convert_tools_openai().
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from .base import BaseAgent
from ..place.tools import convert_tools_openai

logger = logging.getLogger(__name__)


class DeepSeekAgent(BaseAgent):
    """DeepSeek V3.2 — sober, direct, a different tradition."""

    def __init__(
        self,
        place_path: Path,
        log_path: Path,
        config: dict[str, Any],
        model: str = "deepseek-chat",
    ):
        super().__init__("deepseek", place_path, log_path, config)
        self.client = AsyncOpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
        self.model = model

    async def send_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> dict:
        """Send a message to DeepSeek and return the parsed response."""
        max_tokens = self.config.get("session", {}).get("max_output_tokens", 8192)

        # Build OpenAI-format messages
        oai_messages = [{"role": "system", "content": system}]
        oai_messages.extend(self._prepare_messages(messages))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = convert_tools_openai()

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

        return self._parse_response(response)

    def _prepare_messages(self, messages: list[dict]) -> list[dict]:
        """Convert our message format to OpenAI chat format."""
        prepared = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                prepared.append({"role": msg["role"], "content": content})
            # TODO: handle tool result messages in OpenAI format
        return prepared

    def _parse_response(self, response) -> dict:
        """Parse an OpenAI-compatible response into our standard format."""
        choice = response.choices[0]
        message = choice.message

        result = {
            "text": message.content or "",
            "tool_calls": [],
            "thinking": None,
            "raw_content": None,
            "usage": {
                "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                "output_tokens": getattr(response.usage, "completion_tokens", 0),
                "thinking_tokens": 0,
            },
            "stop_reason": choice.finish_reason or "end_turn",
        }

        if message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return result
