"""STT data tayyorlash — o'zbek ASR datasetlarini Whisper formatiga birlashtiradi.

Manbalar (ochiq, litsenziyaga bog'liq emas):
  - USC            (issai/Uzbek_Speech_Corpus)        — 105 soat, 958 ovoz
  - Common Voice   (mozilla-foundation/common_voice_17_0, "uz")
  - FLEURS         (google/fleurs, "uz_uz")

Chiqish: HF DatasetDict (train/validation/test) — har bir namuna:
  {"audio": {16kHz mono}, "sentence": "<tozalangan lotin matn>"}
`save_to_disk` bilan saqlanadi; train_whisper.py shundan o'qiydi.

Ishlatish:
  python ml/stt/prepare_data.py --out data/stt_uz --sources usc,cv,fleurs
  # cheklangan test uchun: --max-per-source 500

DIQQAT: USC/CV katta — internetdan yuklab oladi. Avval kichik --max-per-source bilan
sinab ko'ring.
"""
from __future__ import annotations

import argparse
import re
import unicodedata

# Lotin o'zbek alifbosida ruxsat etilgan belgilar (apostroflar normallashtiriladi)
_APOS = {"`": "ʻ", "'": "ʻ", "‘": "ʻ", "’": "ʻ", "ʼ": "ʻ"}
_KEEP = re.compile(r"[^a-zoʻgʻsh\sʻ\d]", re.IGNORECASE)


def normalize_uz(text: str) -> str:
    """O'zbek lotin matnini ASR uchun normallashtirish.

    - kichik harf
    - apostrof variantlarini bitta ʻ ga keltirish (oʻ, gʻ)
    - punktuatsiyani olib tashlash (ASR target uchun soddalashtiramiz)
    - ortiqcha bo'shliqlarni siqish
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    for k, v in _APOS.items():
        text = text.replace(k, v)
    text = text.lower()
    # harf, raqam, bo'shliq va ʻ dan boshqasini bo'shliqqa
    text = re.sub(r"[^\w\sʻ]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_usc(max_n=None):
    from datasets import load_dataset
    ds = load_dataset("issai/Uzbek_Speech_Corpus")
    # USC ustun nomi odatda "transcription" yoki "sentence" — ikkalasini ham qo'llaymiz
    def pick(b):
        return b.get("transcription") or b.get("sentence") or b.get("text") or ""
    return _to_common(ds, pick, max_n)


def _load_cv(max_n=None):
    from datasets import load_dataset
    ds = load_dataset("mozilla-foundation/common_voice_17_0", "uz")
    return _to_common(ds, lambda b: b.get("sentence", ""), max_n)


def _load_fleurs(max_n=None):
    from datasets import load_dataset
    ds = load_dataset("google/fleurs", "uz_uz")
    return _to_common(ds, lambda b: b.get("transcription") or b.get("raw_transcription") or "", max_n)


def _to_common(ds, text_fn, max_n):
    """HF DatasetDict ni umumiy {audio, sentence} ga keltiradi (16kHz)."""
    from datasets import Audio, DatasetDict

    out = DatasetDict()
    for split in ds:
        d = ds[split]
        if max_n:
            d = d.select(range(min(max_n, len(d))))
        d = d.map(lambda b: {"sentence": normalize_uz(text_fn(b))})
        d = d.filter(lambda b: len(b["sentence"]) >= 2)
        d = d.cast_column("audio", Audio(sampling_rate=16000))
        keep = [c for c in d.column_names if c not in ("audio", "sentence")]
        d = d.remove_columns(keep)
        out[split] = d
    return out


# Split nomlarini standartlashtirish (har dataset turlicha nomlaydi)
_SPLIT_ALIAS = {
    "train": "train", "validation": "validation", "dev": "validation",
    "validated": "train", "test": "test",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="chiqish papkasi (save_to_disk)")
    ap.add_argument("--sources", default="usc,cv,fleurs")
    ap.add_argument("--max-per-source", type=int, default=None)
    args = ap.parse_args()

    from datasets import DatasetDict, concatenate_datasets

    loaders = {"usc": _load_usc, "cv": _load_cv, "fleurs": _load_fleurs}
    buckets: dict[str, list] = {"train": [], "validation": [], "test": []}

    for src in [s.strip() for s in args.sources.split(",") if s.strip()]:
        if src not in loaders:
            print(f"⚠️  noma'lum manba: {src}")
            continue
        print(f"→ {src} yuklanmoqda...")
        dd = loaders[src](args.max_per_source)
        for split, d in dd.items():
            tgt = _SPLIT_ALIAS.get(split, "train")
            buckets[tgt].append(d)
            print(f"   {src}/{split} → {tgt}: {len(d)} namuna")

    final = DatasetDict()
    for split, parts in buckets.items():
        if parts:
            final[split] = concatenate_datasets(parts).shuffle(seed=42)
    # validation/test bo'sh bo'lsa train'dan ajratamiz
    if "train" in final and "validation" not in final:
        s = final["train"].train_test_split(test_size=0.02, seed=42)
        final["train"], final["validation"] = s["train"], s["test"]

    print("Jami:", {k: len(v) for k, v in final.items()})
    final.save_to_disk(args.out)
    print(f"✅ saqlandi: {args.out}")


if __name__ == "__main__":
    main()
