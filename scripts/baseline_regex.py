"""Regex-only baseline — measures leak rate when only regex patterns are used (no NER model)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.regex_engine import RegexPHIAnalyzer

gold = [json.loads(l) for l in Path("data/eval/gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
analyzer = RegexPHIAnalyzer()
leaks = sum(
    1 for note in gold
    if any(ent["text"] not in " ".join(s.text for s in analyzer.analyze(note["text"]))
           for ent in note.get("entities", []))
)
print(f"pure_regex leak rate: {leaks / len(gold) * 100:.1f}%")
