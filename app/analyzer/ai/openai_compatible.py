"""OpenAI-compatible chat-completions provider.

Works with OpenAI, DeepSeek, Ollama and any gateway that exposes
``POST {base_url}/chat/completions``.  Includes timeouts, bounded exponential
backoff for transient failures (429/5xx/timeouts) and strict response
validation.  API keys never appear in raised error messages.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.analyzer.ai.base import AIInsight, AIProviderError, AnalysisContext, parse_insight_payload
from app.analyzer.ai.prompts import SYSTEM_PROMPT, build_user_prompt

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
MAX_RESPONSE_BYTES = 1_000_000

SleepFunction = Callable[[float], Awaitable[None]]


class OpenAICompatibleProvider:
    """Async provider for OpenAI-style ``/chat/completions`` APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        name: str = "openai_compatible",
        timeout: float = 30.0,
        max_retries: int = 2,
        temperature: float = 0.2,
        http_client: httpx.AsyncClient | None = None,
        sleep: SleepFunction = asyncio.sleep,
        use_response_format: bool = True,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not model:
            raise ValueError("model is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = name
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.temperature = temperature
        self._http_client = http_client
        self._sleep = sleep
        self._use_response_format = use_response_format

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _build_payload(self, context: AnalysisContext) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(context)},
            ],
            "temperature": self.temperature,
            "max_tokens": 900,
            "stream": False,
        }
        if self._use_response_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._http_client is not None:
            return await self._http_client.post(
                self.endpoint, json=payload, headers=headers, timeout=self.timeout
            )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(self.endpoint, json=payload, headers=headers)

    async def analyze(self, context: AnalysisContext) -> AIInsight:
        payload = self._build_payload(context)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._post(payload)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise AIProviderError("The AI provider timed out", provider=self.name) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise AIProviderError(
                    "The AI provider could not be reached", provider=self.name
                ) from exc

            if response.status_code >= 400:
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise AIProviderError(
                    f"The AI provider returned HTTP {response.status_code}", provider=self.name
                )

            content = self._extract_content(response)
            return parse_insight_payload(
                content,
                provider=self.name,
                model=self.model,
            )

        raise AIProviderError("The AI provider is unavailable", provider=self.name) from last_error

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(0.5 * (2**attempt), 5.0)

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise AIProviderError("The AI provider response is too large")
        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError("The AI provider returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise AIProviderError("The AI provider returned an invalid response payload")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("The AI provider response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise AIProviderError("The AI provider response has no message")
        content = message.get("content")
        if isinstance(content, list):
            # Newer APIs may return content as a list of parts.
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            )
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("The AI provider returned an empty message")
        return content
