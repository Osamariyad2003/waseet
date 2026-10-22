"""Gemini-backed implementation of `AIGateway`.

Only the provider specifics live here. Structured output is obtained by
asking for JSON (`response_mime_type`) with the agent's schema stated in the
prompt, then parsing the returned text. All orchestration, parsing and
guardrails are shared in `base.py`, so a deal verified by Gemini is judged
by exactly the same rules as one verified by Anthropic.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from app.config import Settings
from app.integrations.ai.base import (
    MAX_TOKENS,
    BaseLLMGateway,
    PermanentModelError,
    TransientModelError,
)

# HTTP statuses worth one retry, mirroring the Anthropic gateway.
_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class GeminiAIGateway(BaseLLMGateway):
    """Structured output via Gemini's JSON mode."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        super().__init__(settings)
        self._client = client
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    @property
    def _provider_name(self) -> str:
        return "GEMINI_API_KEY"

    def _is_configured(self) -> bool:
        return self._settings.gemini_configured

    async def _single_call(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        image: tuple[str, str] | None,
    ) -> dict[str, Any]:
        from google.genai import types
        from google.genai.errors import APIError

        # Gemini's schema subset is finicky, so the exact output shape is
        # stated in the prompt and the response is plain JSON — robust across
        # SDK versions, and the base layer validates it regardless.
        prompt = (
            f"{user}\n\nRespond with a single JSON object that matches this schema "
            f"exactly, and nothing else:\n{json.dumps(tool['input_schema'])}"
        )

        parts: list[Any] = [types.Part.from_text(text=prompt)]
        if image is not None:
            media_type, data = image
            if media_type and data:
                try:
                    parts.append(
                        types.Part.from_bytes(data=base64.b64decode(data), mime_type=media_type)
                    )
                except (ValueError, TypeError):
                    # A corrupt image is not worth a retry; let the verifier
                    # judge the text it can see.
                    pass

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.2,
                ),
            )
        except APIError as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            message = f"the model call failed ({status or type(exc).__name__})"
            raise (
                TransientModelError(message)
                if status in _TRANSIENT_STATUS
                else PermanentModelError(message)
            ) from exc

        text = _response_text(response)
        if not text:
            raise TransientModelError("the model returned no content")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Sometimes the model wraps JSON in prose or a code fence.
            payload = _loads_embedded_json(text)
            if payload is None:
                raise TransientModelError("the model did not return parseable JSON") from None
        if not isinstance(payload, dict):
            raise TransientModelError("the model did not return a JSON object")
        return payload


def _response_text(response: Any) -> str:
    """The text of a Gemini response, tolerant of SDK shape differences."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    # Fall back to walking candidates/parts.
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                return part_text
    return ""


def _loads_embedded_json(text: str) -> Any | None:
    """Pull the first balanced JSON object out of a response that wrapped it
    in a code fence or prose."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
