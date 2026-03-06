"""
Gemini agent for Palimpsest — the Other.

Uses the Google GenAI SDK. Enters during Phase 2.
Tool conversion is handled by the centralised convert_tools_gemini().
"""

from __future__ import annotations

import logging
import os
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
        self._client = None
        self.model = model

    @property
    def client(self) -> genai.Client:
        """Lazy client creation — only connects when actually needed."""
        if self._client is None:
            if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
                raise ValueError(
                    "No Gemini API key found. Set GOOGLE_API_KEY in your .env file. "
                    "Get a key at https://ai.google.dev/gemini-api/docs/api-key"
                )
            self._client = genai.Client()
        return self._client

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

        # Build config — omit system_instruction when empty (same as
        # Claude's omitted system parameter)
        config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if tools:
            config_kwargs["tools"] = convert_tools_gemini(tools)

        config = types.GenerateContentConfig(**config_kwargs)

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
        """Convert our message format to Gemini's Content format.

        Handles three kinds of content:
        - Plain strings (text messages)
        - Lists with function_call blocks (model responses with tool use)
        - Lists with function_response blocks (tool results)
        """
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]

            if isinstance(content, str):
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=content)],
                ))
            elif isinstance(content, list):
                parts = []
                for item in content:
                    item_type = item.get("type")
                    if item_type == "text" and item.get("text"):
                        parts.append(types.Part.from_text(text=item["text"]))
                    elif item_type == "function_call":
                        parts.append(types.Part.from_function_call(
                            name=item["name"],
                            args=item.get("args", {}),
                        ))
                    elif item_type == "function_response":
                        parts.append(types.Part.from_function_response(
                            name=item["name"],
                            response=item["response"],
                        ))
                if parts:
                    contents.append(types.Content(role=role, parts=parts))

        return contents

    def _parse_response(self, response) -> dict:
        """Parse a Gemini response into our standard format."""
        result = {
            "text": "",
            "tool_calls": [],
            "thinking": None,
            "raw_content": [],
            "usage": {
                "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                "thinking_tokens": getattr(response.usage_metadata, "thinking_token_count", 0) if hasattr(response.usage_metadata, "thinking_token_count") else 0,
            },
            "stop_reason": "end_turn",
        }

        text_parts = []
        raw_content = []

        if response.candidates:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "thought") and part.thought:
                    # Gemini thinking/reasoning content
                    result["thinking"] = part.text
                    raw_content.append({
                        "type": "thinking",
                        "thinking": part.text,
                    })
                elif part.text:
                    text_parts.append(part.text)
                    raw_content.append({
                        "type": "text",
                        "text": part.text,
                    })
                elif part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    result["tool_calls"].append({
                        "id": fc.name,  # Gemini doesn't use separate IDs
                        "name": fc.name,
                        "arguments": args,
                    })
                    raw_content.append({
                        "type": "function_call",
                        "name": fc.name,
                        "args": args,
                    })

            # Map Gemini finish reasons to our standard format
            # Gemini: STOP (normal), MAX_TOKENS, SAFETY, RECITATION
            # Our format: end_turn (normal), max_tokens, etc.
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason:
                fr_str = str(finish_reason).upper()
                if "STOP" in fr_str:
                    result["stop_reason"] = "end_turn"
                elif "MAX_TOKENS" in fr_str:
                    result["stop_reason"] = "max_tokens"
                else:
                    result["stop_reason"] = fr_str.lower()

        result["text"] = "\n".join(text_parts)
        result["raw_content"] = raw_content
        return result

    def _format_assistant_message(self, response: dict) -> list[dict]:
        """Format assistant response for conversation history.

        Returns raw content blocks so _prepare_messages can reconstruct
        the Gemini Content objects with function_call parts intact.
        Same pattern as Claude's raw_content approach.
        """
        return response.get("raw_content", [{"type": "text", "text": response.get("text", "")}])

    def _format_tool_results(self, results: list[dict]) -> list[dict]:
        """Format tool results as Gemini FunctionResponse blocks.

        Returns structured dicts that _prepare_messages converts to
        Part.from_function_response() objects.
        """
        return [
            {
                "type": "function_response",
                "name": r["name"],
                "response": {"result": r["result"]},
            }
            for r in results
        ]
