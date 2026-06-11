"""Security AI qatlami — bildirishnoma hodisasini LLM bilan tahlil qiladi.

Vazifa: xom hodisani olib, severity (info/warning/critical), qisqa o'zbekcha
xulosa va tavsiya etilgan harakatni qaytaradi. LLM mavjud bo'lmasa yoki
`security_ai_enabled=False` bo'lsa — rule-based (qoidaga asoslangan) fallback
ishlaydi, ya'ni tizim AI'siz ham xabar beradi.

LLM mavjud `api/services/llm/registry.py` (Groq/OpenAI/...) orqali chaqiriladi.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from api.services import platform

log = logging.getLogger(__name__)

VALID_SEVERITY = {"info", "warning", "critical"}

# Kategoriya → odatiy severity (rule-based fallback uchun)
_CATEGORY_SEVERITY = {
    "payment": "critical",
    "auth": "warning",
    "security": "critical",
    "database": "critical",
    "yandex": "warning",
    "ai_agent": "warning",
    "notifier": "info",
}

_SYSTEM_PROMPT = (
    "Sen restoran SaaS platformasining xavfsizlik analitiklasan. "
    "Senga tizim hodisasi (kategoriya, xom xabar, kontekst) beriladi. "
    "Sen FAQAT JSON qaytarasan, boshqa hech narsa yozmaysan. JSON sxemasi:\n"
    '{"severity": "info|warning|critical", "summary": "<1-2 jumla o\'zbekcha tushuntirish>", '
    '"action": "<admin nima qilishi kerakligi, qisqa o\'zbekcha>"}\n'
    "severity tanlashda: pul/to'lov/ma'lumotlar bazasi/xavfsizlik buzilishi = critical; "
    "shubhali urinish/ogohlantirish = warning; oddiy ma'lumot = info. "
    "summary qisqa, aniq va inson o'qiy oladigan bo'lsin."
)


def _ai_enabled() -> bool:
    # Default True — super-admin o'chirmaguncha AI ishlaydi
    val = platform.get("security_ai_enabled")
    return True if val is None else bool(val)


def _rule_based(category: str, raw_message: str, severity_hint: str | None) -> dict:
    """LLM'siz fallback — kategoriya va hint asosida severity + sodda xulosa."""
    sev = (severity_hint or "").lower()
    if sev not in VALID_SEVERITY:
        sev = _CATEGORY_SEVERITY.get(category, "warning")
    summary = (raw_message or "Tizim hodisasi").strip()
    if len(summary) > 300:
        summary = summary[:300] + "…"
    return {"severity": sev, "summary": summary, "action": "", "ai_used": False}


def _safe_parse(content: str) -> dict | None:
    """LLM javobidan JSON ajratib olish (ba'zan ortiqcha matn bilan keladi)."""
    if not content:
        return None
    text = content.strip()
    # ```json ... ``` bloklarini tozalash
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        # Birinchi { ... } bo'lagini izlash
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                return None
    return None


async def analyze(
    category: str,
    raw_message: str,
    context: dict[str, Any] | None,
    severity_hint: str | None = None,
) -> dict:
    """Hodisani tahlil qilib {severity, summary, action, ai_used} qaytaradi.

    Hech qachon exception ko'tarmaydi — xatoda rule-based fallback'ga tushadi.
    """
    if not _ai_enabled():
        return _rule_based(category, raw_message, severity_hint)

    try:
        from api.services.llm.registry import get_provider, get_provider_api_key
        provider = get_provider()
        api_key = get_provider_api_key()
        if not api_key:
            return _rule_based(category, raw_message, severity_hint)
        model = (platform.get("ai_llm_model") or "").strip()
        if not model:
            # Provayderning birinchi modeli
            models = getattr(provider, "models", [])
            model = models[0].value if models else ""
        if not model:
            return _rule_based(category, raw_message, severity_hint)

        event = {
            "category": category,
            "message": raw_message,
            "context": {k: str(v)[:200] for k, v in (context or {}).items()},
            "severity_hint": severity_hint,
        }
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(event, ensure_ascii=False)},
        ]
        result = await provider.chat(api_key, model, messages, [])
        parsed = _safe_parse(getattr(result, "content", "") or "")
        if not parsed:
            return _rule_based(category, raw_message, severity_hint)

        sev = str(parsed.get("severity", "")).lower()
        if sev not in VALID_SEVERITY:
            sev = _rule_based(category, raw_message, severity_hint)["severity"]
        summary = str(parsed.get("summary") or raw_message or "").strip()[:500]
        action = str(parsed.get("action") or "").strip()[:300]
        return {"severity": sev, "summary": summary, "action": action, "ai_used": True}
    except Exception as e:
        log.warning("security_ai.analyze LLM xatosi, fallback: %s", e)
        return _rule_based(category, raw_message, severity_hint)
