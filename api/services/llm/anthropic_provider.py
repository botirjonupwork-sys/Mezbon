"""Anthropic Claude adapter — Messages API + tool_use bloklari.

OpenAI'dan farqlar:
  - Endpoint: /v1/messages
  - Auth: x-api-key header (Bearer emas)
  - system prompt — alohida `system` field, messages ichida emas
  - tool_use va tool_result bloklari (assistant content massivida)
"""
from __future__ import annotations

import json
from typing import ClassVar

import httpx

from .base import LLMProvider, ChatResult, ModelInfo


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    display_name = "Anthropic Claude"
    requires_billing = True
    api_key_prefix = "sk-ant-"
    api_key_help_url = "https://console.anthropic.com/settings/keys"

    BASE_URL: ClassVar[str] = "https://api.anthropic.com/v1/messages"
    API_VERSION: ClassVar[str] = "2023-06-01"

    @property
    def models(self) -> list[ModelInfo]:
        return [
            ModelInfo("claude-haiku-4-5", "Claude Haiku 4.5 (tez, arzon)", context=200_000, notes="~$1.00/$5.00 per 1M"),
            ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6 (balansli)", context=200_000, notes="~$3.00/$15.00 per 1M"),
            ModelInfo("claude-opus-4-7", "Claude Opus 4.7 (eng aqlli)", context=200_000, notes="~$15/$75 per 1M"),
        ]

    @staticmethod
    def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        """OpenAI shaklidagi xabarlarni Anthropic Messages API formatiga aylantirish."""
        system_parts: list[str] = []
        result: list[dict] = []

        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""

            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            if role == "user":
                result.append({"role": "user", "content": content})
                continue

            if role == "assistant":
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else fn.get("arguments") or {}
                    except json.JSONDecodeError:
                        args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id") or "",
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                if blocks:
                    result.append({"role": "assistant", "content": blocks})
                continue

            if role == "tool":
                # OpenAI tool roli → Anthropic'da user message ichida tool_result bloki
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id") or "",
                        "content": content,
                    }],
                })
                continue

        return ("\n".join(system_parts), result)

    @staticmethod
    def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
        out = []
        for t in tools or []:
            fn = t.get("function", {})
            out.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        return out

    async def chat(self, api_key, model, messages, tools):
        system, msgs = self._to_anthropic_messages(messages)
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": 0.4,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._to_anthropic_tools(tools)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(self.BASE_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        content_text = ""
        tool_calls = []
        for block in data.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                content_text += block.get("text", "")
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name", ""),
                    "arguments": block.get("input") or {},
                })

        usage = data.get("usage") or {}
        return ChatResult(
            content=content_text,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": int(usage.get("input_tokens") or 0),
                "completion_tokens": int(usage.get("output_tokens") or 0),
            },
        )
