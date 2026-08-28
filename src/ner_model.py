import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re
import logging
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
        adapter_dir = Path("models/adapter")
        has_local_weights = (
            adapter_dir.exists() and 
            (adapter_dir / "config.json").exists() and
            ((adapter_dir / "model.safetensors").exists() or (adapter_dir / "pytorch_model.bin").exists())
        )
        if model_name:
            self.model_name = model_name
        elif has_local_weights:
            self.model_name = "models/adapter"
            logger.info("[NER] Loading fine-tuned local model: models/adapter")
        else:
            self.model_name = "thomas-sounack/BioClinical-ModernBERT-base"
            logger.info(f"[NER] Loading base model fallback: {self.model_name}")

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
            logger.info(f"[NER Pipeline] Loaded BioClinical-ModernBERT model from '{self.model_name}'")
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
        if not entity_group:
            return None, ""
        group = entity_group.upper().strip()
        if group.startswith("B-") or group.startswith("I-"):
            group = group[2:]

        mapping = {
            # NAMES
            "NAME": (HIPAACategory.NAMES, "NAME"),
            "PERSON": (HIPAACategory.NAMES, "NAME"),
            "PATIENT": (HIPAACategory.NAMES, "NAME"),
            "DOCTOR": (HIPAACategory.NAMES, "NAME"),
            "PER": (HIPAACategory.NAMES, "NAME"),

            # GEOGRAPHY
            "LOCATION": (HIPAACategory.GEOGRAPHY, "LOCATION"),
            "LOC": (HIPAACategory.GEOGRAPHY, "LOCATION"),
            "GEO": (HIPAACategory.GEOGRAPHY, "LOCATION"),
            "ADDRESS": (HIPAACategory.GEOGRAPHY, "LOCATION"),
            "HOSPITAL": (HIPAACategory.GEOGRAPHY, "FACILITY"),
            "FACILITY": (HIPAACategory.GEOGRAPHY, "FACILITY"),
            "CLINIC": (HIPAACategory.GEOGRAPHY, "FACILITY"),
            "ORG": (HIPAACategory.GEOGRAPHY, "FACILITY"),

            # DATES & AGES
            "DATE": (HIPAACategory.DATES_AGES, "DATE"),
            "AGE": (HIPAACategory.DATES_AGES, "AGE"),

            # CONTACT / PHONE / EMAIL / FAX
            "PHONE": (HIPAACategory.PHONE, "PHONE"),
            "FAX": (HIPAACategory.FAX, "FAX"),
            "EMAIL": (HIPAACategory.EMAIL, "EMAIL"),
            "CONTACT": (HIPAACategory.PHONE, "CONTACT"),

            # IDENTIFIERS
            "SSN": (HIPAACategory.SSN, "SSN"),
            "MRN": (HIPAACategory.MRN, "MRN"),
            "HEALTH_PLAN": (HIPAACategory.HEALTH_PLAN, "HEALTH_PLAN"),
            "ACCOUNT": (HIPAACategory.ACCOUNT, "ACCOUNT"),
            "CERTIFICATE": (HIPAACategory.CERTIFICATE, "CERTIFICATE"),
            "VEHICLE": (HIPAACategory.VEHICLE, "VEHICLE"),
            "DEVICE": (HIPAACategory.DEVICE, "DEVICE"),
            "URL": (HIPAACategory.URL, "URL"),
            "IP": (HIPAACategory.IP, "IP"),
            "ID": (HIPAACategory.OTHER_ID, "ID"),
            "OTHER_ID": (HIPAACategory.OTHER_ID, "ID"),
            "PROFESSION": (HIPAACategory.OTHER_ID, "PROFESSION"),
        }

        if group in mapping:
            return mapping[group]

        if "NAME" in group or "PER" in group:
            return HIPAACategory.NAMES, "NAME"
        if "LOC" in group or "GEO" in group or "ADDRESS" in group:
            return HIPAACategory.GEOGRAPHY, "LOCATION"
        if "HOSP" in group or "FACIL" in group or "CLINIC" in group:
            return HIPAACategory.GEOGRAPHY, "FACILITY"
        if "DATE" in group:
            return HIPAACategory.DATES_AGES, "DATE"
        if "AGE" in group:
            return HIPAACategory.DATES_AGES, "AGE"
        if "PHONE" in group or "TEL" in group:
            return HIPAACategory.PHONE, "PHONE"
        if "EMAIL" in group:
            return HIPAACategory.EMAIL, "EMAIL"
        if "SSN" in group:
            return HIPAACategory.SSN, "SSN"
        if "MRN" in group:
            return HIPAACategory.MRN, "MRN"
        if "ID" in group:
            return HIPAACategory.OTHER_ID, "ID"

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

    def get_model_diagnostics(self) -> dict:
        import torch
        adapter_dir = Path("models/adapter")
        has_local_weights = (
            adapter_dir.exists() and 
            (adapter_dir / "config.json").exists() and
            ((adapter_dir / "model.safetensors").exists() or (adapter_dir / "pytorch_model.bin").exists())
        )
        cuda_avail = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "N/A"
        
        num_labels = 0
        id2label = {}
        param_count = 0
        architecture = "Unknown"
        
        if self.pipeline and hasattr(self.pipeline, "model"):
            m = self.pipeline.model
            param_count = sum(p.numel() for p in m.parameters())
            architecture = m.__class__.__name__
            if hasattr(m.config, "id2label"):
                id2label = m.config.id2label
                num_labels = len(id2label)
        
        return {
            "model_path": self.model_name,
            "fine_tuned_weights_exist": has_local_weights,
            "FINE_TUNED_MODEL_AVAILABLE": has_local_weights,
            "architecture": architecture,
            "parameter_count": param_count,
            "number_of_labels": num_labels,
            "id2label": id2label,
            "device": "cuda:0" if cuda_avail else "cpu",
            "cuda_available": cuda_avail,
            "gpu_name": gpu_name,
            "is_fine_tuned": has_local_weights,
            "is_fallback": not has_local_weights,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = TransformerPHIAnalyzer()
    diag = analyzer.get_model_diagnostics()
    print("\n" + "=" * 60)
    print("         NER MODEL DIAGNOSTIC AUDIT REPORT")
    print("=" * 60)
    print(f"Model Path                   : {diag['model_path']}")
    print(f"FINE_TUNED_MODEL_AVAILABLE   : {diag['FINE_TUNED_MODEL_AVAILABLE']}")
    print(f"Fine-Tuned Weights Exist     : {diag['fine_tuned_weights_exist']}")
    print(f"Architecture                 : {diag['architecture']}")
    print(f"Parameter Count              : {diag['parameter_count']:,}")
    print(f"Number of Labels             : {diag['number_of_labels']}")
    print(f"Device                       : {diag['device']}")
    print(f"CUDA Available               : {diag['cuda_available']}")
    print(f"GPU Name                     : {diag['gpu_name']}")
    print(f"Is Fine-Tuned                : {diag['is_fine_tuned']}")
    print(f"Is Fallback                  : {diag['is_fallback']}")
    print("=" * 60 + "\n")

