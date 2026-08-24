from typing import List
from src.config import HIPAACategory
from src.regex_engine import RegexPHIAnalyzer, PHISpan
from src.ner_model import TransformerPHIAnalyzer


class HybridPHIAnalyzer:

    def __init__(self):
        self.regex_analyzer = RegexPHIAnalyzer()
        self.ner_analyzer = TransformerPHIAnalyzer()

    def analyze(self, text: str) -> List[PHISpan]:
        regex_spans = self.regex_analyzer.analyze(text)
        ner_spans = self.ner_analyzer.analyze(text)
        all_spans: List[PHISpan] = []

        for s in regex_spans:
            s.score = 1.00 if s.category not in (HIPAACategory.NAMES, HIPAACategory.GEOGRAPHY) else 0.90
            all_spans.append(s)
        for s in ner_spans:
            s.score = 0.98 if s.category == HIPAACategory.NAMES else 0.88
            all_spans.append(s)

        sorted_spans = sorted(all_spans, key=lambda s: (s.score, s.end - s.start), reverse=True)
        resolved: List[PHISpan] = []
        for candidate in sorted_spans:
            if not any(not (candidate.end <= k.start or candidate.start >= k.end) for k in resolved):
                resolved.append(candidate)

        return sorted(resolved, key=lambda s: s.start)
