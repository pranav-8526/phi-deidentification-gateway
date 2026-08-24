"""Presidio baseline — measures leak rate using transformer/spaCy analyzer alone."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.ner_model import TransformerPHIAnalyzer

gold = [json.loads(l) for l in Path("data/eval/gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
analyzer = TransformerPHIAnalyzer()
leaks = sum(
    1 for note in gold
    if any(ent["text"] not in " ".join(s.text for s in analyzer.analyze(note["text"]))
           for ent in note.get("entities", []))
)
print(f"spacy_baseline leak rate: {leaks / len(gold) * 100:.1f}%")
