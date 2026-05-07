"""Legal hujjatlarni serve qiluvchi route — ToS, Privacy, Refund.

Mijoz va restoranlar uchun ochiq, autentifikatsiya talab qilmaydi.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse


router = APIRouter(prefix="/legal", tags=["legal"])

LEGAL_DIR = Path(__file__).parent.parent.parent / "docs" / "legal"

DOCS = {
    "terms": "TERMS_OF_SERVICE.md",
    "privacy": "PRIVACY_POLICY.md",
    "refund": "REFUND_POLICY.md",
}


@router.get("/")
async def list_documents():
    """Mavjud huquqiy hujjatlar ro'yxati."""
    return {
        "documents": [
            {"id": k, "title": v.replace("_", " ").replace(".md", ""), "url": f"/legal/{k}"}
            for k, v in DOCS.items()
        ]
    }


@router.get("/{doc_id}", response_class=PlainTextResponse)
async def get_document(doc_id: str):
    """Hujjat matnini Markdown formatida qaytaradi."""
    filename = DOCS.get(doc_id)
    if not filename:
        raise HTTPException(404, "Hujjat topilmadi")
    path = LEGAL_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Fayl topilmadi")
    return path.read_text(encoding="utf-8")
