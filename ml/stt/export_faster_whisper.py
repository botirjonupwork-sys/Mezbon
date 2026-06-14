"""Fine-tune qilingan Whisper → faster-whisper (CTranslate2) — CPU inference.

Production server'da GPU yo'q — faster-whisper int8 bilan CPU'da tez ishlaydi.

Ishlatish:
  python ml/stt/export_faster_whisper.py --model out/whisper-uz-small --out out/fw-uz --quant int8

Keyin inference (production, BEPUL):
  from faster_whisper import WhisperModel
  m = WhisperModel("out/fw-uz", device="cpu", compute_type="int8")
  segments, info = m.transcribe("audio.ogg", language="uz")
  text = " ".join(s.text for s in segments)
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="fine-tune qilingan HF model papkasi")
    ap.add_argument("--out", required=True)
    ap.add_argument("--quant", default="int8", choices=["int8", "int8_float16", "float16", "float32"])
    args = ap.parse_args()

    # ctranslate2 transformers converter
    cmd = [
        "ct2-transformers-converter",
        "--model", args.model,
        "--output_dir", args.out,
        "--copy_files", "tokenizer.json", "preprocessor_config.json",
        "--quantization", args.quant,
        "--force",
    ]
    print("→", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print("❌ konvertatsiya xato. `pip install ctranslate2 transformers` tekshiring.")
        sys.exit(rc)
    print(f"✅ faster-whisper model: {args.out}")
    print("voice.py ga ulash: ai_stt_provider=local, WhisperModel(out, device='cpu', compute_type='int8')")


if __name__ == "__main__":
    main()
