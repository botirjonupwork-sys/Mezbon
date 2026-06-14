"""Whisper'ni o'zbekchaga fine-tune qilish (HF Transformers Seq2SeqTrainer).

GPU kerak. prepare_data.py tayyorlagan datasetdan o'qiydi.

Ishlatish (cloud GPU mashinada):
  python ml/stt/train_whisper.py \
    --data data/stt_uz --model openai/whisper-small \
    --out out/whisper-uz-small --epochs 3 --batch 16

Model tanlovi (CPU inference tezligi vs aniqlik):
  whisper-small  (244M) — CPU'da tez, yaxshi (TAVSIYA boshlash uchun)
  whisper-medium (769M) — aniqroq, sekinroq
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

import torch


@dataclass
class Collator:
    processor: Any

    def __call__(self, features: list[dict]) -> dict:
        # input_features (log-mel) ni pad qilamiz
        inputs = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(inputs, return_tensors="pt")
        # label (token id) larni pad qilamiz
        labels = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(labels, return_tensors="pt")
        lab = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)
        # boshidagi BOS tokenni olib tashlaymiz (Trainer o'zi qo'shadi)
        if (lab[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            lab = lab[:, 1:]
        batch["labels"] = lab
        return batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="openai/whisper-small")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-5)
    args = ap.parse_args()

    from datasets import load_from_disk
    import evaluate
    from transformers import (
        WhisperProcessor, WhisperForConditionalGeneration,
        Seq2SeqTrainer, Seq2SeqTrainingArguments,
    )

    processor = WhisperProcessor.from_pretrained(args.model, language="uzbek", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(args.model)
    model.generation_config.language = "uzbek"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None

    ds = load_from_disk(args.data)

    def prep(batch):
        audio = batch["audio"]
        batch["input_features"] = processor.feature_extractor(
            audio["array"], sampling_rate=16000
        ).input_features[0]
        batch["labels"] = processor.tokenizer(batch["sentence"]).input_ids
        return batch

    ds = ds.map(prep, remove_columns=ds["train"].column_names, num_proc=2)

    metric = evaluate.load("wer")

    def compute_wer(pred):
        pred_ids, label_ids = pred.predictions, pred.label_ids
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        pred_str = processor.tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        ref_str = processor.tokenizer.batch_decode(label_ids, skip_special_tokens=True)
        return {"wer": 100 * metric.compute(predictions=pred_str, references=ref_str)}

    targs = Seq2SeqTrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=1,
        learning_rate=args.lr,
        warmup_steps=500,
        num_train_epochs=args.epochs,
        fp16=torch.cuda.is_available(),
        eval_strategy="epoch",
        save_strategy="epoch",
        predict_with_generate=True,
        generation_max_length=225,
        logging_steps=25,
        report_to=["tensorboard"],
        load_best_model_at_end=True,
        metric_for_best_model="wer",
        greater_is_better=False,
    )

    trainer = Seq2SeqTrainer(
        args=targs,
        model=model,
        train_dataset=ds["train"],
        eval_dataset=ds.get("validation") or ds.get("test"),
        data_collator=Collator(processor),
        compute_metrics=compute_wer,
        tokenizer=processor.feature_extractor,
    )

    trainer.train()
    trainer.save_model(args.out)
    processor.save_pretrained(args.out)
    print(f"✅ model saqlandi: {args.out}")
    print("Keyingi qadam: export_faster_whisper.py bilan CPU inference'ga eksport")


if __name__ == "__main__":
    main()
