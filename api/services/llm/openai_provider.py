"""OpenAI Chat Completions adapter."""
from __future__ import annotations

import json
from typing import ClassVar

import httpx

from .base import LLMProvider, ChatResult, ModelInfo


class OpenAIProvider(LLMProvider):
    name = "openai"
    display_name = "OpenAI (GPT)"
    requires_billing = True
    api_key_prefix = "sk-"
    api_key_help_url = "https://platform.openai.com/api-keys"

    BASE_URL: ClassVar[str] = "https://api.openai.com/v1"

    @property
    def models(self) -> list[ModelInfo]:
        return [
            ModelInfo("gpt-4o-mini", "gpt-4o-mini (tez, arzon)", context=128_000, notes="$0.15/$0.60 per 1M"),
            ModelInfo("gpt-4o", "gpt-4o (aniqroq)", context=128_000, notes="$2.50/$10.00 per 1M"),
            ModelInfo("gpt-4.1-mini", "gpt-4.1-mini", context=1_000_000, notes="$0.40/$1.60 per 1M"),
            ModelInfo("gpt-4.1", "gpt-4.1", context=1_000_000, notes="$2.00/$8.00 per 1M"),
        ]

    async def chat(self, api_key, model, messages, tools):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.4,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{self.BASE_URL}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage") or {}

        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc.get("function", {}).get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.get("id"),
                "name": tc.get("function", {}).get("name", ""),
                "arguments": args,
            })

        return ChatResult(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            },
        )
