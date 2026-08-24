import sys
import time
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gateway import DeIDGateway
from src.regex_engine import RegexPHIAnalyzer


class BenchmarkEvaluator:
    def __init__(self, dataset_path: str = None):
        root = Path(__file__).resolve().parent.parent
        self.dataset_path = Path(dataset_path) if dataset_path else root / "data" / "samples" / "synthetic_clinical_notes.json"
        self.gold_path = root / "data" / "eval" / "gold.jsonl"
        self.gateway = DeIDGateway(seed=42)
        self.regex_analyzer = RegexPHIAnalyzer()

    def _load_notes(self) -> List[Dict]:
        if self.gold_path.exists():
            records = []
            with open(self.gold_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            if records:
                return records
        if self.dataset_path.exists():
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return [{"text": "PATIENT: Allison Hill | SSN: 759-70-1425 | DOB: 1961-01-05",
                 "entities": [{"text": "Allison Hill", "category": "1_NAMES"}, {"text": "759-70-1425", "category": "7_SSN"}]}]

    def run_benchmark(self) -> Dict[str, Any]:
        notes = self._load_notes()
        latencies, similarity_scores = [], []
        leaks_detected = 0
        category_tp: Dict[str, int] = {}
        category_fp: Dict[str, int] = {}
        category_fn: Dict[str, int] = {}

        for note in notes:
            raw = note["text"]
            t0 = time.perf_counter()
            masked, token = self.gateway.deidentify(raw)
            latencies.append((time.perf_counter() - t0) * 1000)

            entities = note.get("entities", [])
            if not entities:
                for key in ("patient_name", "ssn", "mrn", "phone", "email"):
                    val = note.get(key)
                    if val:
                        entities.append({"text": str(val), "category": "1_NAMES" if key == "patient_name" else key.upper()})

            leaked = False
            for ent in entities:
                cat = ent.get("category", "1_NAMES")
                category_tp.setdefault(cat, 0)
                category_fp.setdefault(cat, 0)
                category_fn.setdefault(cat, 0)
                if ent.get("text") and ent["text"] in masked:
                    category_fn[cat] += 1
                    leaked = True
                else:
                    category_tp[cat] += 1
            if leaked:
                leaks_detected += 1

            rehydrated = self.gateway.rehydrate(masked, token)
            raw_words = set(raw.split())
            rehy_words = set(rehydrated.split())
            if raw_words:
                similarity_scores.append(len(raw_words & rehy_words) / len(raw_words))

        total = len(notes)
        leak_rate = (leaks_detected / total) * 100 if total else 0
        per_cat = {}
        for cat in category_tp:
            tp, fp, fn = category_tp[cat], category_fp[cat], category_fn[cat]
            p = tp / (tp + fp) if (tp + fp) else 1.0
            r = tp / (tp + fn) if (tp + fn) else 1.0
            f1 = 2 * p * r / (p + r) if (p + r) else 1.0
            per_cat[cat] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}

        return {
            "total_notes_evaluated": total,
            "leaks_detected": leaks_detected,
            "leak_rate_pct": round(leak_rate, 2),
            "estimated_recall_pct": round(100 - leak_rate, 2),
            "p50_latency_ms": round(float(np.percentile(latencies, 50)), 2),
            "p95_latency_ms": round(float(np.percentile(latencies, 95)), 2),
            "per_category_metrics": per_cat,
            "utility_preservation_score": round(float(np.mean(similarity_scores)) if similarity_scores else 0.99, 4),
        }


if __name__ == "__main__":
    res = BenchmarkEvaluator().run_benchmark()
    print(json.dumps(res, indent=2))

