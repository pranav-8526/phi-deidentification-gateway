import json
from pathlib import Path
from huggingface_hub import hf_hub_download
from datasets import load_dataset, Dataset
from transformers import AutoTokenizer, AutoModelForTokenClassification, TrainingArguments, Trainer, DataCollatorForTokenClassification
import torch

MODEL_NAME = "thomas-sounack/BioClinical-ModernBERT-base"

ENTITY_TYPES = [
    "NAME", "DATE", "LOCATION", "AGE", "ID", "CONTACT",
    "PHONE", "EMAIL", "SSN", "MRN", "ACCOUNT", "DEVICE",
    "VEHICLE", "URL", "IP", "HEALTH_PLAN", "CERTIFICATE", "OTHER_ID",
]
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
assert n_params == 149633317 and n_params <= 1000000000

raw = load_dataset("json", data_files=hf_hub_download("temlm-foundation/Technetium-I", "train.jsonl", repo_type="dataset"), split="train[:50000]")
print(f"Loaded {len(raw)} Technetium-I notes")

TYPE_MAP = {}
for row in raw.select(range(min(500, len(raw)))):
    for ent in row.get("entities", []):
        lbl = ent.get("label", ent.get("type", "OTHER_ID")).upper()
        if lbl not in TYPE_MAP:
            mapped = lbl
            for et in ENTITY_TYPES:
                if et in lbl or lbl in et:
                    mapped = et
                    break
            TYPE_MAP[lbl] = mapped
print(f"Entity type mapping: {TYPE_MAP}")


def tokenize_with_labels(examples):
    tokenized = tok(
        examples["text"], truncation=True, max_length=512,
        padding="max_length", return_offsets_mapping=True,
    )
    all_labels = []
    for idx, offsets in enumerate(tokenized["offset_mapping"]):
        labels = [0] * len(offsets)
        entities = examples.get("entities", [None] * len(examples["text"]))[idx]
        if entities:
            for ent in entities:
                raw_type = ent.get("label", ent.get("type", "OTHER_ID")).upper()
                mapped_type = TYPE_MAP.get(raw_type, "OTHER_ID")
                b_id = label2id.get(f"B-{mapped_type}", 0)
                i_id = label2id.get(f"I-{mapped_type}", 0)
                start, end = ent["start"], ent["end"]
                first = True
                for j, (ts, te) in enumerate(offsets):
                    if ts is None or te is None or ts == te:
                        labels[j] = -100
                        continue
                    if ts >= start and te <= end:
                        labels[j] = b_id if first else i_id
                        first = False
        for j, (ts, te) in enumerate(offsets):
            if ts is None or te is None:
                labels[j] = -100
        all_labels.append(labels)
    tokenized["labels"] = all_labels
    tokenized.pop("offset_mapping")
    return tokenized


ds = Dataset.from_dict({
    "text": [ex["text"] for ex in raw],
    "entities": [ex.get("entities", []) for ex in raw],
})
tok_ds = ds.map(tokenize_with_labels, batched=True, remove_columns=["text", "entities"])


class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get("logits")
        import torch.nn as nn
        w = torch.ones(len(label_list), device=logits.device)
        w[1::2] = 3.0
        loss_fct = nn.CrossEntropyLoss(weight=w, ignore_index=-100)
        loss = loss_fct(logits.view(-1, len(label_list)), labels.view(-1))
        return (loss, outputs) if return_outputs else loss


args = TrainingArguments(
    output_dir="models/adapter", per_device_train_batch_size=16,
    learning_rate=2e-5, num_train_epochs=3, save_total_limit=1,
    logging_steps=50, report_to="none",
)
trainer = WeightedTrainer(
    model=model, args=args, train_dataset=tok_ds,
    data_collator=DataCollatorForTokenClassification(tok),
)
trainer.train()
trainer.save_model("models/adapter")
tok.save_pretrained("models/adapter")
print(f"Final model.num_parameters()={n_params} saved to models/adapter/")
