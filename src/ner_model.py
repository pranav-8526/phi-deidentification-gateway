import re
import logging
from pathlib import Path
from typing import List
from src.config import HIPAACategory
from src.regex_engine import PHISpan
from src.eponym_whitelist import EponymDisambiguator

logger = logging.getLogger(__name__)

_SPACY_NLP = None

_HONORIFIC_RE = re.compile(
    r'\b(mr|dr|ms|mrs|prof|patient|pt|attending|physician|referring|guarantor|doctor)\.?\s*$'
)

_BARE_NAME_RE = re.compile(r'\b[A-Z][a-z]{1,}(?:,\s+|\s+)[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})?\b')

_STOP_PHRASES = {
    "medical record", "discharge summary", "physical therapy", "radiology report",
    "left l5", "right l5", "parkinson disease", "alzheimer disease", "blood pressure",
    "emergency department", "primary care", "safe harbor", "clinical note",
    "patient name", "provider name", "physician name", "doctor name", "emergency contact",
    "rochester clinic", "cleveland clinic", "mayo clinic", "parkinson", "alzheimer",
}


def _get_spacy_nlp():
    global _SPACY_NLP
    if _SPACY_NLP is None:
        try:
            import spacy
            try:
                _SPACY_NLP = spacy.load("en_core_web_sm")
            except Exception:
                _SPACY_NLP = spacy.blank("en")
        except Exception as e:
            logger.warning(f"spaCy unavailable: {e}")
    return _SPACY_NLP


def _is_person_context(text: str, start: int) -> bool:
    left = text[max(0, start - 20):start].strip().lower()
    return bool(_HONORIFIC_RE.search(left))


def _is_eponym(word: str, text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 30):min(len(text), end + 30)]
    if _is_person_context(text, start):
        return False
    return EponymDisambiguator.is_medical_term(word, context)


def _overlaps(start: int, end: int, spans: List[PHISpan]) -> bool:
    return any(not (end <= s.start or start >= s.end) for s in spans)


class TransformerPHIAnalyzer:
    def __init__(self, model_name: str = None):
        adapter = Path("models/adapter/pytorch_model.bin")
        default = "models/adapter" if adapter.exists() else "thomas-sounack/BioClinical-ModernBERT-base"
        self.model_name = model_name or default
        self.pipeline = None
        self._init_model()

    def _init_model(self):
        try:
            from transformers import pipeline
            import torch
            if not torch.cuda.is_available():
                torch.set_num_threads(4)
            device = 0 if torch.cuda.is_available() else -1
            self.pipeline = pipeline(
                "token-classification",
                model=self.model_name,
                aggregation_strategy="simple",
                device=device,
                ignore_labels=[],
            )
            logger.info(f"[NER Pipeline] Loaded BioClinical-ModernBERT model from '{self.model_name}' (149M params)")
        except Exception as e:
            logger.warning(f"Transformer model unavailable ({e}). Falling back to spaCy.")
            self.pipeline = None

    def _chunk_text(self, text: str) -> list:
        lines = text.split("\n")
        chunks, current, current_len, offset, acc = [], [], 0, 0, 0
        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > 1536:
                if current:
                    chunks.append((offset, "\n".join(current)))
                offset = acc
                current = [line]
                current_len = line_len
            else:
                current.append(line)
                current_len += line_len
            acc += line_len
        if current:
            chunks.append((offset, "\n".join(current)))
        return chunks

    def _map_entity(self, entity_group: str):
        group = entity_group.upper()
        name_tags = ("PER", "PERSON", "NAME", "PATIENT", "DOCTOR")
        loc_tags = ("LOC", "LOCATION", "GEO", "CITY", "STATE", "ADDRESS")
        org_tags = ("ORG", "HOSPITAL", "FACILITY", "CLINIC")
        if any(t in group for t in name_tags):
            return HIPAACategory.NAMES, "NAME"
        if any(t in group for t in loc_tags):
            return HIPAACategory.GEOGRAPHY, "LOCATION"
        if any(t in group for t in org_tags):
            return HIPAACategory.GEOGRAPHY, "FACILITY"
        return None, group

    def analyze(self, text: str) -> List[PHISpan]:
        spans: List[PHISpan] = []

        if self.pipeline:
            try:
                import torch
                chunks = self._chunk_text(text)
                chunk_texts = [c[1] for c in chunks]
                if chunk_texts:
                    with torch.inference_mode():
                        all_results = self.pipeline(chunk_texts, batch_size=16)
                    for (chunk_offset, _), results in zip(chunks, all_results):
                        for res in results:
                            word = res.get("word", "").strip()
                            start = chunk_offset + res.get("start", 0)
                            end = chunk_offset + res.get("end", 0)
                            category, label = self._map_entity(res.get("entity_group", ""))
                            if category and word and not _is_eponym(word, text, start, end):
                                if not _overlaps(start, end, spans):
                                    spans.append(PHISpan(
                                        start=start, end=end, text=text[start:end],
                                        category=category, label=label,
                                        score=float(res.get("score", 0.90)),
                                    ))
            except Exception as e:
                logger.warning(f"Transformer execution error: {e}")

        if not self.pipeline:
            nlp = _get_spacy_nlp()
            if nlp:
                try:
                    doc = nlp(text)
                    for ent in doc.ents:
                        category, label = None, ent.label_
                        if ent.label_ == "PERSON":
                            category, label = HIPAACategory.NAMES, "NAME"
                        elif ent.label_ in ("GPE", "LOC", "FAC", "ORG"):
                            category, label = HIPAACategory.GEOGRAPHY, "LOCATION"
                        if category and not _is_eponym(ent.text, text, ent.start_char, ent.end_char):
                            if not _overlaps(ent.start_char, ent.end_char, spans):
                                spans.append(PHISpan(
                                    start=ent.start_char, end=ent.end_char, text=ent.text,
                                    category=category, label=label, score=0.88,
                                ))
                except Exception as e:
                    logger.warning(f"spaCy execution error: {e}")

        for m in _BARE_NAME_RE.finditer(text):
            candidate = m.group(0)
            ctx = text[max(0, m.start() - 30):min(len(text), m.end() + 30)]
            if candidate.lower() in _STOP_PHRASES:
                continue
            if EponymDisambiguator.is_medical_term(candidate, ctx):
                continue
            if not _overlaps(m.start(), m.end(), spans):
                spans.append(PHISpan(
                    start=m.start(), end=m.end(), text=candidate,
                    category=HIPAACategory.NAMES, label="NAME", score=0.85,
                ))

        return spans
