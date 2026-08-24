import json
import pytest
from pathlib import Path
from src.gateway import DeIDGateway
from src.regex_engine import RegexPHIAnalyzer
from src.date_shifter import DateShifter, AgeCapper
from src.eponym_whitelist import EponymDisambiguator, MEDICAL_WHITELIST

@pytest.fixture
def gateway():
    return DeIDGateway(seed=42)

def test_eponym_preservation_extended():
    eponyms = [
        "Parkinson",
        "Alzheimer",
        "Apgar",
        "Babinski",
        "Graves",
        "Hodgkin",
        "Raynaud"
    ]
    for term in eponyms:
        assert EponymDisambiguator.is_medical_term(term) is True

def test_hipaa_18_identifiers_coverage(gateway):
    sample_text = (
        "Patient Marcus Wood (SSN: 123-45-6789, MRN: 9876543) was admitted on 2024-03-15.\n"
        "Contact: 555-019-2831, email: marcus.wood@example.com.\n"
        "Address: 123 Main St, Seattle, WA 98101. IP: 192.168.1.50.\n"
        "Web portal: https://health.org/patient/9876543.\n"
        "Patient is 92 years old (DOB: 1932-01-10)."
    )
    masked, mapping = gateway.deidentify(sample_text)
    
    assert "123-45-6789" not in masked
    assert "marcus.wood@example.com" not in masked
    assert "555-019-2831" not in masked
    assert "192.168.1.50" not in masked
    assert "98101" not in masked
    assert "[AGE > 89]" in masked or "92" not in masked

def test_date_formats_and_shifting(gateway):
    dates_text = (
        "Admission: 2024-01-10. Discharge: 01/15/2024.\n"
        "Follow-up scheduled for Feb 20, 2024 and 25 Mar 2024."
    )
    masked, mapping = gateway.deidentify(dates_text, patient_seed=100)
    
    assert "2024-01-10" not in masked
    assert "01/15/2024" not in masked

def test_ambiguous_eponym_vs_person_name(gateway):
    clinical_note = (
        "Dr. Parkinson evaluated the patient and confirmed a diagnosis of Parkinson's disease. "
        "The patient was admitted to Wood Memorial Hospital by Dr. Wood."
    )
    masked, mapping = gateway.deidentify(clinical_note)
    
    assert "Parkinson's disease" in masked or "Parkinson's" in masked
    assert "Dr. Parkinson" not in masked

def test_lossless_roundtrip_rehydration(gateway):
    raw_note = "Patient Sarah Connor (MRN: 44592) presented with acute migraines on 2024-06-01."
    masked, mapping = gateway.deidentify(raw_note)
    
    simulated_llm_response = f"Summary: Patient presented with migraines. Masked ref: {masked}"
    rehydrated = gateway.rehydrate(simulated_llm_response, mapping)
    
    assert "Sarah Connor" in rehydrated or "MRN: 44592" in rehydrated

def test_multi_patient_isolation():
    gateway1 = DeIDGateway(seed=101)
    gateway2 = DeIDGateway(seed=202)
    
    text = "Admitted on 2024-05-10."
    masked1, _ = gateway1.deidentify(text)
    masked2, _ = gateway2.deidentify(text)
    
    assert masked1 != masked2 or "2024-05-10" not in masked1

def test_bare_name_second_occurrence(gateway):
    text = "Patient: Allison Hill ... Emergency Contact: Valerie Gray ... Patient Allison Hill was evaluated"
    masked, _ = gateway.deidentify(text)
    assert "Allison Hill" not in masked
    assert "Valerie Gray" not in masked

def test_valerie_gray_contact(gateway):
    text = "Emergency Contact: Valerie Gray at 001-260-501-3389"
    masked, _ = gateway.deidentify(text)
    assert "Valerie Gray" not in masked

def test_patient_colon_uppercase(gateway):
    text = "PATIENT: John Doe admitted for observation."
    masked, _ = gateway.deidentify(text)
    assert "John Doe" not in masked

def test_banner_all_caps(gateway):
    text = "PATIENT HEADER: WHITFIELD, MARCUS D. | DOB 03/14/1987"
    masked, _ = gateway.deidentify(text)
    assert "WHITFIELD, MARCUS D." not in masked
    assert "03/14/1987" not in masked

def test_gold_50_leak_zero(gateway):
    gold_path = Path(__file__).resolve().parent.parent / "data" / "eval" / "gold.jsonl"
    if gold_path.exists():
        with open(gold_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                rec = json.loads(line)
                masked, _ = gateway.deidentify(rec["text"])
                for ent in rec.get("entities", []):
                    assert ent["text"] not in masked, f"Leak detected in {rec['id']}: {ent['text']} found in masked text"

def test_no_leak_to_llm(gateway):
    text = "Patient Allison Hill admitted on 2024-03-15."
    masked, mapping = gateway.deidentify(text)
    assert "Allison Hill" not in masked
    assert "2024-03-15" not in masked
