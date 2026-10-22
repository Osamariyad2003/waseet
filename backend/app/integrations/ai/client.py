"""Anthropic-backed implementation of `AIGateway`.

Only the provider specifics live here: the API call and how a structured
result is extracted from a forced tool call. All the agent orchestration,
output parsing and guardrails are shared in `base.py`.
"""

from __future__ import annotations

from typing import Any

from anthropic import APIError, APIStatusError, AsyncAnthropic

from app.config import Settings
from app.integrations.ai.base import (
    MAX_TOKENS,
    BaseLLMGateway,
    PermanentModelError,
    TransientModelError,
)


class AnthropicAIGateway(BaseLLMGateway):
    """Structured output via a forced tool call."""

    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        super().__init__(settings)
        self._client = client or AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.ai_timeout_seconds,
            max_retries=0,  # retries are handled in the base, so they stay auditable
        )

    @property
    def _provider_name(self) -> str:
        return "ANTHROPIC_API_KEY"

    def _is_configured(self) -> bool:
        return self._settings.ai_configured

    async def _single_call(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        image: tuple[str, str] | None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": _message_content(user, image)}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
            )
        except APIStatusError as exc:
            error = f"the model returned HTTP {exc.status_code}"
            raise (
                TransientModelError(error)
                if _is_transient_status(exc.status_code)
                else PermanentModelError(error)
            ) from exc
        except APIError as exc:
            raise TransientModelError(f"the model call failed ({type(exc).__name__})") from exc

        payload = _extract_tool_input(response, tool["name"])
        if payload is None:
            raise TransientModelError("the model did not return the expected structured output")
        return payload


def _message_content(user: str, image: tuple[str, str] | None) -> Any:
    """A plain string, or text plus an image block. The image goes after the
    text, so the instructions and data boundary come first."""
    if image is None:
        return user
    media_type, data = image
    if not media_type or not data:
        return user
    return [
        {"type": "text", "text": user},
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
    ]


def _is_transient_status(status_code: int) -> bool:
    return status_code == 408 or status_code == 429 or status_code >= 500


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any] | None:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            payload = getattr(block, "input", None)
            if isinstance(payload, dict):
                return payload
    return None
