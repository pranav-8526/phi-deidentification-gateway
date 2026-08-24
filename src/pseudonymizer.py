import re
import json
from typing import Dict, List, Tuple
from src.config import HIPAACategory, PSEUDONYM_PREFIXES
from src.regex_engine import PHISpan
from src.date_shifter import DateShifter, AgeCapper, _NON_AGE_CONTEXT, _AGE_PATTERN
from src.eponym_whitelist import EponymDisambiguator

_HONORIFIC_RE = re.compile(
    r'\b(mr|dr|ms|mrs|prof|patient|pt|attending|physician|referring|guarantor|doctor)\.?\s*$'
)
_COMMON_WORDS = {"date", "name", "male", "female", "patient", "doctor"}


class Pseudonymizer:
    def __init__(self, date_shifter: DateShifter):
        self.date_shifter = date_shifter
        self.entity_counts: Dict[str, int] = {}
        self.value_to_pseudonym: Dict[str, str] = {}
        self.mapping: Dict[str, str] = {}

    def get_pseudonym(self, raw_value: str, category: HIPAACategory) -> str:
        key = raw_value.strip().lower()
        if key in self.value_to_pseudonym:
            return self.value_to_pseudonym[key]
        prefix = PSEUDONYM_PREFIXES.get(category, "PHI")
        count = self.entity_counts.get(prefix, 0) + 1
        self.entity_counts[prefix] = count
        pseudonym = f"[{prefix}_{count}]"
        self.value_to_pseudonym[key] = pseudonym
        self.mapping[pseudonym] = raw_value.strip()
        return pseudonym

    def mask_text(self, text: str, spans: List[PHISpan]) -> Tuple[str, Dict[str, str]]:
        sorted_spans = sorted(spans, key=lambda s: s.start, reverse=True)
        non_overlapping: List[PHISpan] = []
        for span in sorted_spans:
            if not any(not (span.end <= k.start or span.start >= k.end) for k in non_overlapping):
                non_overlapping.append(span)

        masked_text = text
        masked_raw_values: List[Tuple[str, str, HIPAACategory]] = []

        for span in non_overlapping:
            raw_val = text[span.start:span.end]
            if span.category == HIPAACategory.DATES_AGES and span.label == "DATE":
                shifted = self.date_shifter.shift_date_str(raw_val)
                pseudonym = self.get_pseudonym(raw_val, span.category)
                self.mapping[pseudonym] = raw_val
                self.mapping[f"{pseudonym}_SHIFTED"] = shifted
            else:
                pseudonym = self.get_pseudonym(raw_val, span.category)
            masked_text = masked_text[:span.start] + pseudonym + masked_text[span.end:]
            masked_raw_values.append((raw_val, pseudonym, span.category))

        for raw_val, pseudonym, category in masked_raw_values:
            if len(raw_val) < 3 or raw_val.lower() in _COMMON_WORDS:
                continue
            pattern = re.compile(re.escape(raw_val), re.IGNORECASE)

            def _replace(match, _pseudo=pseudonym):
                word = match.group(0)
                start = match.start()
                ctx = masked_text[max(0, start - 30):min(len(masked_text), start + len(word) + 30)]
                left = masked_text[max(0, start - 20):start].strip().lower()
                if not _HONORIFIC_RE.search(left) and EponymDisambiguator.is_medical_term(word, ctx):
                    return word
                return _pseudo

            masked_text = pattern.sub(_replace, masked_text)

        original_ages = []
        for m in _AGE_PATTERN.finditer(masked_text):
            num_str = m.group(2)
            try:
                age_val = int(num_str)
            except ValueError:
                continue
            start_idx = m.start(2)
            left = masked_text[max(0, start_idx - 25):start_idx].strip().lower()
            right = masked_text[start_idx + len(num_str):min(len(masked_text), start_idx + len(num_str) + 25)].strip().lower()
            if left.endswith("-"):
                continue
            if right.startswith("-") and not right.startswith("-year"):
                continue
            if any(w in left for w in _NON_AGE_CONTEXT):
                continue
            if age_val > 89:
                original_ages.append(num_str)

        if original_ages:
            self.mapping["_AGE_OVER_89_LIST"] = json.dumps(original_ages)

        masked_text = AgeCapper.cap_ages_in_text(masked_text)
        return masked_text, self.mapping
