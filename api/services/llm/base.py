"""LLM provayder asosiy interfeysi.

Har bir provayder shu asosga ergashishi kerak. Normalizatsiya qilingan format:

  Input messages — OpenAI shaklida:
    [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "...", "tool_calls": [...]},
      {"role": "tool", "tool_call_id": "...", "content": "..."}
    ]

  Input tools — OpenAI shaklida:
    [
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    ]

  Output:
    ChatResult{
      content: str,                        # assistant matni
      tool_calls: [                        # mavjud bo'lsa
        {"id": str, "name": str, "arguments": dict}
      ],
      usage: {"prompt_tokens": int, "completion_tokens": int}
    }
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # [{id, name, arguments}]
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


@dataclass
class ModelInfo:
    value: str            # API model ID
    label: str            # UI ko'rsatma
    free: bool = False    # bepul rejimda mavjudmi
    context: int = 8192   # token kontekst oynasi
    notes: str = ""       # qo'shimcha izoh


class LLMProvider(ABC):
    name: str = ""        # 'openai' | 'groq' | 'anthropic' | 'gemini'
    display_name: str = ""
    requires_billing: bool = True   # True bo'lsa hisobda kredit kerak
    api_key_prefix: str = ""        # masalan 'sk-', 'gsk_', 'sk-ant-', 'AIza'
    api_key_help_url: str = ""      # kalitni qaerdan olish

    @property
    @abstractmethod
    def models(self) -> list[ModelInfo]:
        """Bu provayder qo'llab-quvvatlovchi modellar ro'yxati."""

    @abstractmethod
    async def chat(
        self,
        api_key: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
    ) -> ChatResult:
        """Chat completion + function calling."""

    def info(self) -> dict[str, Any]:
        """UI uchun provayder metama'lumotlari."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "requires_billing": self.requires_billing,
            "api_key_prefix": self.api_key_prefix,
            "api_key_help_url": self.api_key_help_url,
            "models": [
                {
                    "value": m.value, "label": m.label,
                    "free": m.free, "context": m.context, "notes": m.notes,
                }
                for m in self.models
            ],
        }
