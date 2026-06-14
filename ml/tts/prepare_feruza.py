"""TTS data tayyorlash — FeruzaSpeech → Piper (LJSpeech) formati.

⚠️ LITSENZIYA: FeruzaSpeech "akademik tadqiqot uchun bepul". Tijoriy (restoran)
foydalanish uchun k2speech.info@gmail.com dan RUXSAT olinishi SHART.
Ruxsatsiz tijoriy modelni ishlatmang. (Bu skript faqat tayyorlash uchun.)

Chiqish (Piper kutadi):
  out/feruza/
    wav/0001.wav, 0002.wav, ...   (22050 Hz mono — Piper standarti)
    metadata.csv                  ("0001|tozalangan lotin matn" qatorlar)

Ishlatish:
  python ml/tts/prepare_feruza.py --out data/tts_feruza --max 0   # 0 = hammasi

Keyin Piper training (github.com/rhasspy/piper, piper_train):
  python -m piper_train.preprocess --language uz --input-dir data/tts_feruza \
      --output-dir data/tts_feruza/proc --sample-rate 22050 --dataset-format ljspeech
  python -m piper_train --dataset-dir data/tts_feruza/proc --batch-size 32 ... \
      --resume_from_checkpoint <bazaviy_vits_checkpoint>   # fine-tune tezroq
"""
from __future__ import annotations

import argparse
import csv
import os

# prepare_data.py'dagi normalizator bilan bir xil (izchillik uchun)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stt"))
from prepare_data import normalize_uz  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=int, default=0, help="0 = hammasi")
    ap.add_argument("--sr", type=int, default=22050)
    args = ap.parse_args()

    import soundfile as sf
    import librosa
    from datasets import load_dataset, Audio

    wav_dir = os.path.join(args.out, "wav")
    os.makedirs(wav_dir, exist_ok=True)

    print("→ FeruzaSpeech (44.1kHz TTS) yuklanmoqda...")
    ds = load_dataset("k2speech/FeruzaSpeech_44100_Hz_tts")
    split = "train" if "train" in ds else list(ds.keys())[0]
    d = ds[split]
    d = d.cast_column("audio", Audio(sampling_rate=args.sr))
    if args.max:
        d = d.select(range(min(args.max, len(d))))

    rows = []
    for i, b in enumerate(d, start=1):
        text = b.get("sentence") or b.get("transcription") or b.get("text") or ""
        text = normalize_uz(text)
        if len(text) < 2:
            continue
        wav = b["audio"]["array"]
        uid = f"{i:05d}"
        sf.write(os.path.join(wav_dir, f"{uid}.wav"), wav, args.sr, subtype="PCM_16")
        rows.append((uid, text))
        if i % 500 == 0:
            print(f"   {i} ta...")

    with open(os.path.join(args.out, "metadata.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|")
        for uid, text in rows:
            w.writerow([uid, text])

    print(f"✅ {len(rows)} namuna tayyor: {args.out}")
    print("Eslatma: tijoriy litsenziya tasdiqlanmaguncha production'da ishlatmang.")


if __name__ == "__main__":
    main()
