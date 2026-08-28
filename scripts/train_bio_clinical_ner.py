import json
from pathlib import Path
from huggingface_hub import hf_hub_download
from datasets import load_dataset, Dataset
from transformers import (
    AutoTokenizer, AutoModelForTokenClassification,
    TrainingArguments, Trainer, DataCollatorForTokenClassification
)
import torch
import numpy as np

MODEL_NAME = "thomas-sounack/BioClinical-ModernBERT-base"

# Explicit list of entity types supported in label scheme
ENTITY_TYPES = [
    "NAME", "DATE", "LOCATION", "AGE", "ID", "CONTACT",
    "PHONE", "EMAIL", "SSN", "MRN", "ACCOUNT", "DEVICE",
    "VEHICLE", "URL", "IP", "HEALTH_PLAN", "CERTIFICATE", "OTHER_ID",
    "HOSPITAL", "PROFESSION",
]

# 20 entity types * 2 (B/I) + 1 (O) = 41 labels
label_list = ["O"] + [f"{p}-{t}" for t in ENTITY_TYPES for p in ("B", "I")]
label2id = {l: i for i, l in enumerate(label_list)}
id2label = {i: l for i, l in enumerate(label_list)}

tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModelForTokenClassification.from_pretrained(
    MODEL_NAME, num_labels=len(label_list),
    id2label=id2label, label2id=label2id,
)
n_params = sum(p.numel() for p in model.parameters())
print(f"model.num_parameters()={n_params}")

raw = load_dataset("json", data_files=hf_hub_download("temlm-foundation/Technetium-I", "train.jsonl", repo_type="dataset"), split="train[:50000]")
print(f"Loaded {len(raw)} Technetium-I notes")

# Map Technetium-I entity types explicitly
TYPE_MAP = {
    "NAME": "NAME",
    "LOCATION": "LOCATION",
    "DATE": "DATE",
    "AGE": "AGE",
    "ID": "ID",
    "PHONE": "PHONE",
    "EMAIL": "EMAIL",
    "CONTACT": "CONTACT",
    "HOSPITAL": "HOSPITAL",
    "PROFESSION": "PROFESSION",
}
for et in ENTITY_TYPES:
    if et not in TYPE_MAP:
        TYPE_MAP[et] = et


def tokenize_with_labels(examples):
    tokenized = tok(
        examples["text"], truncation=True, max_length=512,
        padding="max_length", return_offsets_mapping=True,
    )
    all_labels = []

    for idx, offsets in enumerate(tokenized["offset_mapping"]):
        labels = [0] * len(offsets)
        annotations = examples.get("phi_annotations", [None] * len(examples["text"]))[idx]
        if annotations:
            sorted_anns = sorted(annotations, key=lambda x: (x.get("start", 0), -x.get("end", 0)))
            for ent in sorted_anns:
                raw_type = str(ent.get("entity_type", "OTHER_ID")).upper()
                mapped_type = TYPE_MAP.get(raw_type, "OTHER_ID")
                b_id = label2id.get(f"B-{mapped_type}", label2id.get("B-OTHER_ID", 0))
                i_id = label2id.get(f"I-{mapped_type}", label2id.get("I-OTHER_ID", 0))
                start, end = ent["start"], ent["end"]
                first = True
                for j, (ts, te) in enumerate(offsets):
                    if ts is None or te is None or ts == te:
                        labels[j] = -100
                        continue
                    # Token overlaps with entity span [start, end]
                    if max(ts, start) < min(te, end):
                        labels[j] = b_id if first else i_id
                        first = False

        for j, (ts, te) in enumerate(offsets):
            if ts is None or te is None or ts == te:
                labels[j] = -100
        all_labels.append(labels)
    tokenized["labels"] = all_labels
    tokenized.pop("offset_mapping")
    return tokenized


class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get("logits")
        import torch.nn as nn
        # Principled weighting: Class 0 (O) = 1.0, all entity classes (B- & I-) = 3.0
        w = torch.ones(len(label_list), device=logits.device)
        w[1:] = 3.0
        loss_fct = nn.CrossEntropyLoss(weight=w, ignore_index=-100)
        loss = loss_fct(logits.view(-1, len(label_list)), labels.view(-1))
        return (loss, outputs) if return_outputs else loss


def compute_metrics(p):
    predictions, labels = p
    predictions = np.argmax(predictions, axis=2)

    total_tokens = 0
    correct_tokens = 0
    entity_tokens = 0
    correct_entity_tokens = 0

    for prediction, label in zip(predictions, labels):
        for pred, ref in zip(prediction, label):
            if ref == -100:
                continue
            total_tokens += 1
            if pred == ref:
                correct_tokens += 1
            if ref != 0:
                entity_tokens += 1
                if pred == ref:
                    correct_entity_tokens += 1

    return {
        "accuracy": correct_tokens / max(1, total_tokens),
        "entity_recall": correct_entity_tokens / max(1, entity_tokens),
    }


def check_gpu_environment(model):
    print("=" * 60)
    print("           GPU ENVIRONMENT & HARDWARE AUDIT")
    print("=" * 60)
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_available}")
    if cuda_available:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"GPU Model:      {gpu_name}")
        print(f"VRAM Available: {gpu_mem:.2f} GB")
    else:
        print("GPU Model:      None (Running on CPU - GPU recommended for fast training)")
    
    device = next(model.parameters()).device
    print(f"Model Device:   {device}")
    print("=" * 60 + "\n")
    return cuda_available


def prepare_training_pipeline(num_samples: int = 50000, is_sanity_check: bool = False):
    print(f"Loading {num_samples} Technetium-I notes for {'SANITY CHECK' if is_sanity_check else 'FULL TRAINING'}...")
    raw = load_dataset("json", data_files=hf_hub_download("temlm-foundation/Technetium-I", "train.jsonl", repo_type="dataset"), split=f"train[:{num_samples}]")

    ds = Dataset.from_dict({
        "text": [ex["text"] for ex in raw],
        "phi_annotations": [ex.get("phi_annotations", []) for ex in raw],
    })

    tok_ds = ds.map(tokenize_with_labels, batched=True, remove_columns=["text", "phi_annotations"])

    split_ds = tok_ds.train_test_split(test_size=0.1, seed=42)
    train_ds = split_ds["train"]
    eval_ds = split_ds["test"]

    output_dir = "models/adapter_sanity" if is_sanity_check else "models/adapter"

    args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,
        num_train_epochs=1 if is_sanity_check else 3,
        max_steps=10 if is_sanity_check else -1,
        save_total_limit=2,
        logging_steps=2 if is_sanity_check else 50,
        eval_strategy="steps",
        eval_steps=5 if is_sanity_check else 500,
        save_strategy="steps",
        save_steps=5 if is_sanity_check else 500,
        load_best_model_at_end=True,
        metric_for_best_model="loss",
        greater_is_better=False,
        report_to="none",
        fp16=torch.cuda.is_available(),
        seed=42,
        disable_tqdm=False,
    )

    trainer = WeightedTrainer(
        model=model, args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        compute_metrics=compute_metrics,
        data_collator=DataCollatorForTokenClassification(tok),
    )

    return trainer


def run_full_training(num_samples: int = 50000, run_sanity_first: bool = True):
    cuda_active = check_gpu_environment(model)
    
    if run_sanity_first:
        print("Step 1/2: Running 100-sample GPU/Model Sanity Check...")
        sanity_trainer = prepare_training_pipeline(num_samples=100, is_sanity_check=True)
        sanity_trainer.train()
        print("✅ Sanity check passed! CUDA, model forward/backward pass, and loss computation verified.\n")
    
    print(f"Step 2/2: Starting Full 3-Epoch Training on {num_samples} records...")
    trainer = prepare_training_pipeline(num_samples=num_samples, is_sanity_check=False)
    
    train_result = trainer.train()
    
    save_path = Path("models/adapter").resolve()
    trainer.save_model(str(save_path))
    tok.save_pretrained(str(save_path))
    
    print("\n" + "=" * 60)
    print("           TRAINING FINISHED SUCCESSFULLY")
    print("=" * 60)
    print(f"Global Steps:     {train_result.global_step}")
    print(f"Training Loss:    {train_result.training_loss:.4f}")
    print(f"Saved Directory:  {save_path}")
    print("Saved Files:")
    for f in save_path.iterdir():
        print(f"  - {f.name} ({f.stat().st_size / (1024*1024):.2f} MB)")
    print("=" * 60 + "\n")
    return trainer


if __name__ == "__main__":
    run_full_training()

