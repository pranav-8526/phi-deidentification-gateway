"""Stock spaCy NER baseline — measures leak rate using off-the-shelf en_core_web_sm (no fine-tuning)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import spacy

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading en_core_web_sm...")
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

gold = [json.loads(l) for l in Path("data/eval/gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
total = len(gold)
leaks = 0
for note in gold:
    doc = nlp(note["text"])
    detected = " ".join(ent.text for ent in doc.ents)
    for ent in note.get("entities", []):
        if ent["text"] not in detected:
            leaks += 1
            break
print(f"stock_spacy (en_core_web_sm) leak rate: {leaks}/{total} = {leaks / total * 100:.1f}%")
