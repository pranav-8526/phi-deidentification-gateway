import pytest
from src.config import HIPAACategory
from src.regex_engine import RegexPHIAnalyzer
from src.date_shifter import DateShifter, AgeCapper
from src.gateway import DeIDGateway

def test_regex_analyzer():
    analyzer = RegexPHIAnalyzer()
    sample_text = (
        "Patient SSN: 123-45-6789. Contact phone: (555) 019-2831. "
        "Email: patient.johndoe@example.com. MRN: MRN-998124. "
        "IP: 192.168.1.1. Visit date: 2024-02-11. Zip: 90210."
    )
    spans = analyzer.analyze(sample_text)
    categories = [s.category.value for s in spans]
    
    assert HIPAACategory.SSN.value in categories
    assert HIPAACategory.PHONE.value in categories
    assert HIPAACategory.EMAIL.value in categories
    assert HIPAACategory.MRN.value in categories
    assert HIPAACategory.IP.value in categories
    assert HIPAACategory.DATES_AGES.value in categories
    assert HIPAACategory.GEOGRAPHY.value in categories

def test_date_shifter_and_age_capper():
    shifter = DateShifter(seed=42)
    original_date = "2024-02-11"
    shifted = shifter.shift_date_str(original_date)
    assert shifted != original_date
    assert len(shifted) == 10
    
    text_with_old_age = "Patient is 94 years old and was admitted yesterday."
    capped = AgeCapper.cap_ages_in_text(text_with_old_age)
    assert "90+" in capped
    assert "94" not in capped

def test_gateway_deidentify_and_rehydrate():
    gateway = DeIDGateway(seed=123)
    raw_clinical_note = (
        "WHITFIELD, MARCUS D. | DOB 03/14/1987 | CLAIM PI-2024-8871\n"
        "Patient SSN: 999-88-7777. Phone: 555-123-4567.\n"
        "Admitted on 02/11/2024 for severe back pain."
    )
    
    masked_text, encrypted_mapping = gateway.deidentify(raw_clinical_note)
    
    assert "999-88-7777" not in masked_text
    assert "555-123-4567" not in masked_text
    assert "02/11/2024" not in masked_text
    assert encrypted_mapping is not None
    
    llm_simulated_output = f"Summary of note:\n{masked_text}"
    restored_text = gateway.rehydrate(llm_simulated_output, encrypted_mapping)
    
    assert "999-88-7777" in restored_text
    assert "555-123-4567" in restored_text
    assert "02/11/2024" in restored_text

def test_roundtrip_integrity():
    gateway = DeIDGateway(seed=999)
    sample = "Patient email is test@med.org and phone is 800-555-0199."
    masked, mapping_token = gateway.deidentify(sample)
    rehydrated = gateway.rehydrate(masked, mapping_token)
    assert rehydrated == sample
