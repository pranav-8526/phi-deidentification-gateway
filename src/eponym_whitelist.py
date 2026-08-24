from typing import Set

MEDICAL_WHITELIST: Set[str] = {
    "parkinson", "parkinson's", "alzheimer", "alzheimer's", "crohn", "crohn's",
    "hodgkin", "hodgkin's", "graves", "graves'", "hashimoto", "hashimoto's",
    "raynaud", "raynaud's", "meniere", "meniere's", "barrett", "barrett's",
    "bell", "bell's", "huntington", "huntington's", "cushing", "cushing's",
    "addison", "addison's", "lou gehrig", "lou gehrig's", "sjogren", "sjogren's",
    "wilson", "wilson's", "paget", "paget's", "marfan", "marfan's",
    "babinski", "tinel", "phalen", "romberg", "apgar", "schober", "trousseau",
    "chvostek", "mcmurray", "lasegue", "kussmaul", "cheyne-stokes", "glasgow",
    "foley", "swan-ganz", "picc", "pacing", "holter", "tenkhoff", "zoll",
    "lasix", "coumadin", "tylenol", "advil", "aspirin", "heparin", "insulin",
    "lisinopril", "metformin", "atorvastatin", "gabapentin", "amoxicillin", "metoprolol",
}

MEDICAL_SUFFIXES = [
    "disease", "syndrome", "catheter", "sign", "test",
    "reflex", "palsy", "triad", "score", "scale",
]


class EponymDisambiguator:
    @staticmethod
    def is_medical_term(word: str, context_window: str = "") -> bool:
        clean = word.strip().lower()
        if clean in MEDICAL_WHITELIST:
            return True
        ctx = context_window.lower()
        return any(
            f"{clean} {s}" in ctx or f"{clean}'s {s}" in ctx
            for s in MEDICAL_SUFFIXES
        )
