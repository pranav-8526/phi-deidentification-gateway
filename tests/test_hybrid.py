import pytest
from src.eponym_whitelist import EponymDisambiguator
from src.hybrid_analyzer import HybridPHIAnalyzer
from src.gateway import DeIDGateway

def test_eponym_whitelist():
    assert EponymDisambiguator.is_medical_term("Parkinson's", "Patient diagnosed with Parkinson's disease.") is True
    assert EponymDisambiguator.is_medical_term("Foley", "Inserted a Foley catheter.") is True
    assert EponymDisambiguator.is_medical_term("Lasix", "Prescribed Lasix 40mg daily.") is True
    assert EponymDisambiguator.is_medical_term("Marcus", "Dr. Marcus examined the patient.") is False

def test_hybrid_analyzer_eponym_protection():
    gateway = DeIDGateway(seed=42)
    sample_text = (
        "Dr. Marcus Whitfield diagnosed the patient with Parkinson's disease. "
        "Patient was prescribed Lasix 20mg."
    )
    masked_text, _ = gateway.deidentify(sample_text)
    
    assert "Parkinson's disease" in masked_text or "Parkinson" in masked_text
    assert "Lasix" in masked_text
