from typing import Tuple, Optional
from src.hybrid_analyzer import HybridPHIAnalyzer
from src.date_shifter import DateShifter
from src.pseudonymizer import Pseudonymizer
from src.rehydrator import Rehydrator


class DeIDGateway:

    def __init__(self, seed: Optional[int] = None):
        self.rehydrator = Rehydrator()
        self.seed = seed
        self.analyzer = HybridPHIAnalyzer()

    def deidentify(self, raw_text: str, patient_seed: Optional[int] = None) -> Tuple[str, str]:
        effective_seed = patient_seed if patient_seed is not None else self.seed
        date_shifter = DateShifter(seed=effective_seed)
        pseudonymizer = Pseudonymizer(date_shifter=date_shifter)
        spans = self.analyzer.analyze(raw_text)
        masked_text, mapping = pseudonymizer.mask_text(raw_text, spans)
        encrypted_mapping = self.rehydrator.encrypt_mapping(mapping)
        return masked_text, encrypted_mapping

    def rehydrate(self, llm_response: str, encrypted_mapping: str) -> str:
        restored_text, _ = self.rehydrator.rehydrate(llm_response, encrypted_mapping)
        return restored_text
