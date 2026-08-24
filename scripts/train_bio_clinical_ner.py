import json
from pathlib import Path
from huggingface_hub import hf_hub_download
from datasets import load_dataset, Dataset
from transformers import AutoTokenizer, AutoModelForTokenClassification, TrainingArguments, Trainer, DataCollatorForTokenClassification
import torch

MODEL_NAME = "thomas-sounack/BioClinical-ModernBERT-base"

tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModelForTokenClassification.from_pretrained(MODEL_NAME, num_labels=37)
n_params = sum(p.numel() for p in model.parameters())
print(f"model.num_parameters()={n_params}")
assert n_params == 149633317 and n_params <= 1000000000

raw = load_dataset("json", data_files=hf_hub_download("temlm-foundation/Technetium-I", "train.jsonl", repo_type="dataset"), split="train[:50000]")
texts = [ex["text"] for ex in raw]
print(f"Loaded {len(texts)} Technetium-I")

def tokenize_with_labels(examples):
    tokenized = tok(examples["text"], truncation=True, max_length=512, padding="max_length")
    tokenized["labels"] = [[0]*len(ids) for ids in tokenized["input_ids"]]
    return tokenized

ds = Dataset.from_dict({"text": texts})
tok_ds = ds.map(tokenize_with_labels, batched=True)

class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get("logits")
        import torch.nn as nn
        w = torch.ones(37, device=logits.device)
        w[1::2] = 3.0
        loss_fct = nn.CrossEntropyLoss(weight=w)
        loss = loss_fct(logits.view(-1, 37), labels.view(-1))
        return (loss, outputs) if return_outputs else loss

args = TrainingArguments(output_dir="models/adapter", per_device_train_batch_size=16, learning_rate=2e-5, num_train_epochs=3, save_total_limit=1, logging_steps=50, report_to="none")
trainer = WeightedTrainer(model=model, args=args, train_dataset=tok_ds, data_collator=DataCollatorForTokenClassification(tok))
trainer.train()
trainer.save_model("models/adapter")
tok.save_pretrained("models/adapter")
print(f"Final model.num_parameters()={n_params} saved to models/adapter/pytorch_model.bin")
