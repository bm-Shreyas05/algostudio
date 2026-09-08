"""LLM provider abstraction.

The engine never depends on a provider being present.  ``NullClient`` is the
fallback, and ``ai_service`` degrades to the deterministic template explainer
with a visible notice rather than returning an error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""


class LLMClient(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse: ...


class NullClient:
    name = "null"
    model = ""

    def available(self) -> bool:
        return False

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        return LLMResponse("", "null", "", error="no LLM provider configured")


class AnthropicClient:
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model
        self._client = None

    def available(self) -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        try:
            client = self._ensure()
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(
                block.text for block in message.content
                if getattr(block, "type", "") == "text"
            )
            return LLMResponse(
                text=text,
                provider=self.name,
                model=self.model,
                tokens_in=getattr(message.usage, "input_tokens", 0),
                tokens_out=getattr(message.usage, "output_tokens", 0),
            )
        except Exception as exc:
            return LLMResponse("", self.name, self.model, error=str(exc)[:300])


def build(provider: str, model: str) -> LLMClient:
    if provider == "null":
        return NullClient()
    if provider in ("anthropic", "auto"):
        client = AnthropicClient(model)
        if client.available():
            return client
        if provider == "anthropic":
            return client   # unavailable; ai_service reports the reason
    return NullClient()
