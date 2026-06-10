"""Google Gemini adapter — generateContent + functionCalling.

Asosiy farqlar OpenAI'dan:
  - Endpoint: /v1beta/models/{model}:generateContent
  - Auth: API kalit query string'da (`?key=...`)
  - Roles: 'user' va 'model' (assistant emas), system → systemInstruction alohida
  - Tools: functionDeclarations massivi
  - Function calling: parts ichida functionCall / functionResponse
"""
from __future__ import annotations

from typing import ClassVar

import httpx

from .base import LLMProvider, ChatResult, ModelInfo


class GeminiProvider(LLMProvider):
    name = "gemini"
    display_name = "Google Gemini (BEPUL tier mavjud)"
    requires_billing = False    # Free tier mavjud
    api_key_prefix = "AIza"
    api_key_help_url = "https://aistudio.google.com/apikey"

    BASE_URL: ClassVar[str] = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                "gemini-2.0-flash", "Gemini 2.0 Flash (tavsiya)",
                free=True, context=1_000_000, notes="Bepul: 15 RPM, 1500/kun",
            ),
            ModelInfo(
                "gemini-2.0-flash-lite", "Gemini 2.0 Flash Lite",
                free=True, context=1_000_000, notes="Bepul, tezroq",
            ),
            ModelInfo(
                "gemini-1.5-flash", "Gemini 1.5 Flash",
                free=True, context=1_000_000, notes="Bepul tier",
            ),
            ModelInfo(
                "gemini-1.5-pro", "Gemini 1.5 Pro (kuchli, pullik)",
                free=False, context=2_000_000, notes="$1.25/$5.00 per 1M",
            ),
        ]

    @staticmethod
    def _to_gemini_contents(messages: list[dict]) -> tuple[str, list[dict]]:
        """OpenAI messages → Gemini `contents` + systemInstruction."""
        system_parts: list[str] = []
        contents: list[dict] = []

        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""

            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            if role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
                continue

            if role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    import json as _j
                    try:
                        args = _j.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else fn.get("arguments") or {}
                    except _j.JSONDecodeError:
                        args = {}
                    parts.append({
                        "functionCall": {
                            "name": fn.get("name", ""),
                            "args": args,
                        }
                    })
                if parts:
                    contents.append({"role": "model", "parts": parts})
                continue

            if role == "tool":
                # functionResponse — Gemini'da user rolida yuboriladi
                import json as _j
                try:
                    response_data = _j.loads(content) if isinstance(content, str) else content
                except _j.JSONDecodeError:
                    response_data = {"result": content}
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": m.get("name", "tool_response"),
                            "response": response_data if isinstance(response_data, dict) else {"result": response_data},
                        }
                    }],
                })
                continue

        return ("\n".join(system_parts), contents)

    @staticmethod
    def _to_gemini_tools(tools: list[dict]) -> list[dict]:
        decls = []
        for t in tools or []:
            fn = t.get("function", {})
            decls.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters") or {"type": "OBJECT", "properties": {}},
            })
        return [{"functionDeclarations": decls}] if decls else []

    async def chat(self, api_key, model, messages, tools):
        system, contents = self._to_gemini_contents(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = self._to_gemini_tools(tools)

        url = f"{self.BASE_URL}/models/{model}:generateContent?key={api_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()

        candidates = data.get("candidates") or []
        if not candidates:
            return ChatResult(content="", tool_calls=[], usage={"prompt_tokens": 0, "completion_tokens": 0})

        first = candidates[0]
        parts = (first.get("content") or {}).get("parts") or []
        content_text = ""
        tool_calls = []

        for i, p in enumerate(parts):
            if "text" in p:
                content_text += p["text"]
            elif "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append({
                    # Gemini tool_use uchun ID bermaydi — sun'iy yaratamiz
                    "id": f"call_{i}",
                    "name": fc.get("name", ""),
                    "arguments": fc.get("args") or {},
                })

        usage = data.get("usageMetadata") or {}
        return ChatResult(
            content=content_text,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": int(usage.get("promptTokenCount") or 0),
                "completion_tokens": int(usage.get("candidatesTokenCount") or 0),
            },
        )
