# O'zbek STT + TTS — o'z modellarimiz

Maqsad: **bir marta o'rgatib, o'z serverimizda bepul ishlatish** (cloud'ga doimiy
to'lovsiz). Sifat + narx. Modellar CPU'da ishlashga mo'ljallangan (GPU faqat
training paytida, bir martalik).

## Tanlangan modellar (CPU'da bepul ishlaydi)

| Vazifa | Model | Inference | Nega |
|---|---|---|---|
| STT (ovoz→matn) | **Whisper** (small/medium) fine-tune → **faster-whisper** (CTranslate2) | CPU | O'zbekka moslashadi, CPU'da tez |
| TTS (matn→ovoz) | **Piper** (VITS) | CPU (hatto RPi) | Yengil, bepul, sifatli |

## Datasetlar

### STT (ko'p, ochiq)
- **USC** — `issai/Uzbek_Speech_Corpus` (105 soat, 958 ovoz) — ASR uchun asosiy
- **Common Voice (uz)** — `mozilla-foundation/common_voice_*`
- **FLEURS (uz)** — `google/fleurs` (uz_uz)
- **FeruzaSpeech** — `k2speech/FeruzaSpeech` (60 soat, ASR ham)
- (qo'shimcha) `murodbek/uzbek-speech-corpus`, `islomov/it_youtube_uzbek_speech_dataset`

### TTS
- **FeruzaSpeech (44.1kHz TTS)** — `k2speech/FeruzaSpeech_44100_Hz_tts`
  - 60 soat, BITTA ayol ovozi (Toshkent), yuqori sifat — Piper uchun ideal
  - ⚠️ **LITSENZIYA: "akademik tadqiqot uchun bepul".** Bizning foydalanish TIJORIY
    (restoran SaaS) → **tijoriy ruxsat uchun `k2speech.info@gmail.com`ga yozish SHART.**
    Ruxsatsiz tijoriy ishlatish — huquqiy muammo. Bu birinchi qadam.
  - Erkak ovoz kerak bo'lsa: keyin alohida yozuv (aktyor) yoki boshqa dataset.

## Bosqichlar

### Faza 0 — tayyorgarlik (GPU'siz, HOZIR)
- [ ] FeruzaSpeech tijoriy litsenziya so'rovi (k2speech.info@gmail.com) — FOYDALANUVCHI
- [ ] `ml/` pipeline kodi: data yuklab tozalash, training config (ready-to-run)
- [ ] Datasetlarni yuklab, hajm/sifatni tekshirish (kichik namuna)

### Faza 1 — STT (~1–3 hafta, GPU kerak)
- [ ] USC + Common Voice + FLEURS → Whisper format (audio 16kHz, transkript tozalash)
- [ ] Whisper-small/medium fine-tune (HF Transformers, lotin yozuvi)
- [ ] Baholash — WER (word error rate) test setda
- [ ] faster-whisper (CTranslate2) ga eksport — CPU inference
- [ ] `api/services/voice.py` ga ulash (mavjud `transcribe()` o'rniga local)

### Faza 2 — TTS (~2–4 hafta, GPU kerak)
- [ ] FeruzaSpeech (44.1kHz) → Piper format (audio + transkript + tekislash)
- [ ] Piper training (VITS) — lotin yozuvi, o'zbek fonemalar
- [ ] Baholash — tinglash (MOS), talaffuz
- [ ] Piper inference server → `voice.py` `synthesize()` ga ulash

## GPU
Hozircha yo'q. Faza 0 GPU'siz. Faza 1-2 uchun cloud rent (RunPod/Vast.ai,
~$0.3–2/soat; Faza 1 ~$100–300). Skriptlar shu Mac'da yoziladi, cloud'da ishga tushadi.

## Inference (production, bepul)
- faster-whisper (small/medium) — CPU'da, server'da
- Piper — CPU'da, server'da
- Ikkalasi `voice.py` ga ulanadi; `ai_stt_provider=local`, `ai_tts_provider=local`.

## Manbalar
- FeruzaSpeech: arxiv.org/abs/2410.00035 · huggingface.co/datasets/k2speech/FeruzaSpeech_44100_Hz_tts
- USC: arxiv.org/pdf/2107.14419 · huggingface.co/datasets/issai/Uzbek_Speech_Corpus
- faster-whisper: github.com/SYSTRAN/faster-whisper
- Piper: github.com/rhasspy/piper
