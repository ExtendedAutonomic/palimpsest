"""
Gemini agent for Palimpsest — the Other.

Uses the Google GenAI SDK. Enters during Phase 2.
Tool conversion is handled by the centralised convert_tools_gemini().
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .base import BaseAgent
from ..place.tools import convert_tools_gemini

logger = logging.getLogger(__name__)


class GeminiAgent(BaseAgent):
    """Gemini 2.5 Pro — pragmatic, structured, a different mind."""

    def __init__(
        self,
        place_path: Path,
        log_path: Path,
        config: dict[str, Any],
        model: str = "gemini-2.5-pro",
    ):
        super().__init__("gemini", place_path, log_path, config)
        self.client = genai.Client()
        self.model = model

    async def send_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> dict:
        """Send a message to Gemini and return the parsed response."""
        max_tokens = self.config.get("session", {}).get("max_output_tokens", 8192)

        # Convert messages to Gemini format
        contents = self._prepare_messages(messages)

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            tools=convert_tools_gemini() if tools else None,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise

        return self._parse_response(response)

    def _prepare_messages(self, messages: list[dict]) -> list[types.Content]:
        """Convert our message format to Gemini's Content format."""
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]
            if isinstance(content, str):
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=content)],
                ))
            # TODO: handle tool result messages
        return contents

    def _parse_response(self, response) -> dict:
        """Parse a Gemini response into our standard format."""
        result = {
            "text": "",
            "tool_calls": [],
            "thinking": None,
            "raw_content": None,
            "usage": {
                "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                "thinking_tokens": 0,
            },
            "stop_reason": "end_turn",
        }

        text_parts = []

        if response.candidates:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                elif part.function_call:
                    fc = part.function_call
                    result["tool_calls"].append({
                        "id": fc.name,  # Gemini doesn't use separate IDs
                        "name": fc.name,
                        "arguments": dict(fc.args) if fc.args else {},
                    })

            # Check finish reason
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason:
                result["stop_reason"] = str(finish_reason)

        result["text"] = "\n".join(text_parts)
        return result
