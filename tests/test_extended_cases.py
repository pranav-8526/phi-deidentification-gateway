import json
import pytest
from datetime import datetime
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


def test_date_shifting_intervals_and_ordering(gateway):
    text = "Milestones: 2025-01-01 (admission), 2025-01-05 (procedure), 2025-02-01 (discharge)."
    masked, mapping = gateway.deidentify(text, patient_seed=42, use_shifted_dates=True)
    
    assert "2025-01-01" not in masked
    assert "2025-01-05" not in masked
    assert "2025-02-01" not in masked
    
    shifter = DateShifter(seed=42)
    s1 = shifter.shift_date_str("2025-01-01")
    s2 = shifter.shift_date_str("2025-01-05")
    s3 = shifter.shift_date_str("2025-02-01")
    
    assert s1 in masked
    assert s2 in masked
    assert s3 in masked
    
    dt1 = datetime.strptime(s1, "%Y-%m-%d")
    dt2 = datetime.strptime(s2, "%Y-%m-%d")
    dt3 = datetime.strptime(s3, "%Y-%m-%d")
    
    assert dt1 < dt2 < dt3
    assert (dt2 - dt1).days == 4
    assert (dt3 - dt1).days == 31
    
    rehydrated = gateway.rehydrate(masked, mapping)
    assert "2025-01-01" in rehydrated
    assert "2025-01-05" in rehydrated
    assert "2025-02-01" in rehydrated


def test_textual_and_ambiguous_date_formats(gateway):
    formats_text = (
        "Dates: January 15, 2025 | March 10, 1980 | 02/11/2024 | 17/02/2024"
    )
    masked, mapping = gateway.deidentify(formats_text, patient_seed=77)
    
    assert "January 15, 2025" not in masked
    assert "March 10, 1980" not in masked
    assert "02/11/2024" not in masked
    assert "17/02/2024" not in masked
    
    rehydrated = gateway.rehydrate(masked, mapping)
    assert "January 15, 2025" in rehydrated
    assert "March 10, 1980" in rehydrated
    assert "02/11/2024" in rehydrated
    assert "17/02/2024" in rehydrated


def test_age_capping_non_age_context_preservation(gateway):
    text = (
        "Patient aged 92 presented with BP 92, weight 92 kg, Room 92, Page 92 of report, "
        "and MRN 929812. Also, patient was 97 years old."
    )
    masked, _ = gateway.deidentify(text)
    
    assert "90+" in masked
    assert "97" not in masked
    assert "BP 92" in masked or "bp 92" in masked.lower()
    assert "Room 92" in masked or "room 92" in masked.lower()
    assert "Page 92" in masked or "page 92" in masked.lower()


def test_adversarial_name_eponym_hospital_cases(gateway):
    text = (
        "Dr. Parkinson evaluated Mr. Wood at Wood Memorial Hospital for Parkinson's disease. "
        "Patient O'Brien-Nakamura presented with Foley catheter and Babinski reflex. "
        "Also noted: JACKSON, May, and Winter."
    )
    masked, mapping = gateway.deidentify(text)
    
    assert "Parkinson's disease" in masked or "Parkinson's" in masked
    assert "Foley catheter" in masked or "Foley" in masked
    assert "Babinski reflex" in masked or "Babinski" in masked
    assert "Dr. Parkinson" not in masked
    assert "Mr. Wood" not in masked
    assert "O'Brien-Nakamura" not in masked


def test_rehydration_tampered_and_unknown_tokens(gateway):
    raw = "Patient test note with token [UNKNOWN_999]."
    masked, mapping = gateway.deidentify(raw)
    
    with pytest.raises(Exception):
        gateway.rehydrate(masked, "INVALID_BASE64_TOKEN_XXXXX")
    
    rehydrated, report = gateway.rehydrator.rehydrate(f"{masked} [UNKNOWN_999]", mapping)
    assert "unmatched_tokens" in report
    assert "[UNKNOWN_999]" in report["unmatched_tokens"]


def test_adjacent_span_merging_exact_roundtrip(gateway):
    sample_text = "Patient John Smith was admitted to City Hospital on January 15, 2025."
    masked, enc_mapping = gateway.deidentify(sample_text)
    
    assert "John Smith" not in masked
    assert "City" not in masked
    assert "January 15, 2025" not in masked
    
    rehydrated = gateway.rehydrate(masked, enc_mapping)
    assert rehydrated == sample_text



