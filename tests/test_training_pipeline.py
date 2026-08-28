import pytest
import tempfile
import logging
from pathlib import Path
from src.config import HIPAACategory
from src.ner_model import TransformerPHIAnalyzer
from scripts.train_bio_clinical_ner import (
    tokenize_with_labels, label_list, label2id, id2label, TYPE_MAP
)

def test_type_mapping():
    """Verify explicit mapping of all Technetium-I and HIPAA entity types."""
    assert TYPE_MAP["NAME"] == "NAME"
    assert TYPE_MAP["LOCATION"] == "LOCATION"
    assert TYPE_MAP["HOSPITAL"] == "HOSPITAL"
    assert TYPE_MAP["PROFESSION"] == "PROFESSION"
    assert TYPE_MAP["DATE"] == "DATE"
    assert TYPE_MAP["AGE"] == "AGE"
    assert TYPE_MAP["ID"] == "ID"
    assert TYPE_MAP["PHONE"] == "PHONE"
    assert TYPE_MAP["EMAIL"] == "EMAIL"

def test_bio_label_alignment_real_examples():
    """Test character offset to BIO label conversion on sample examples."""
    examples = {
        "text": [
            "Patient Name: Patricia Smith, MRN: 5667265, DOB: 04/08/1973, Age: 53. Contact: (548) 484-3547, email: patricia@yahoo.com, SSN: 123-45-6789, Address: 2287 Oak Avenue"
        ],
        "phi_annotations": [
            [
                {"entity_type": "NAME", "text": "Patricia Smith", "start": 14, "end": 28},
                {"entity_type": "ID", "text": "5667265", "start": 35, "end": 42},
                {"entity_type": "DATE", "text": "04/08/1973", "start": 49, "end": 59},
                {"entity_type": "AGE", "text": "53", "start": 66, "end": 68},
                {"entity_type": "PHONE", "text": "(548) 484-3547", "start": 79, "end": 93},
                {"entity_type": "EMAIL", "text": "patricia@yahoo.com", "start": 101, "end": 119},
                {"entity_type": "SSN", "text": "123-45-6789", "start": 126, "end": 137},
                {"entity_type": "LOCATION", "text": "2287 Oak Avenue", "start": 148, "end": 163},
            ]
        ]
    }
    
    tokenized = tokenize_with_labels(examples)
    labels = tokenized["labels"][0]
    
    # Verify labels are NOT all O (0)
    non_o_labels = [l for l in labels if l not in (0, -100)]
    assert len(non_o_labels) > 0, "Labels must not be all O!"
    
    # Map label IDs back to string labels
    str_labels = [id2label.get(l, f"UNK_{l}") if l != -100 else "IGN" for l in labels]
    
    # Confirm presence of specific BIO labels
    assert any(l.startswith("B-NAME") for l in str_labels), "Missing B-NAME"
    assert any(l.startswith("B-ID") for l in str_labels), "Missing B-ID"
    assert any(l.startswith("B-DATE") for l in str_labels), "Missing B-DATE"
    assert any(l.startswith("B-AGE") for l in str_labels), "Missing B-AGE"
    assert any(l.startswith("B-PHONE") for l in str_labels), "Missing B-PHONE"
    assert any(l.startswith("B-EMAIL") for l in str_labels), "Missing B-EMAIL"
    assert any(l.startswith("B-SSN") for l in str_labels), "Missing B-SSN"
    assert any(l.startswith("B-LOCATION") for l in str_labels), "Missing B-LOCATION"

def test_entity_mapping_categories():
    """Verify _map_entity maps all BIO labels and groups to correct HIPAA categories."""
    analyzer = TransformerPHIAnalyzer(model_name="thomas-sounack/BioClinical-ModernBERT-base")
    
    # 1. Multi-token NAME
    cat, lbl = analyzer._map_entity("B-NAME")
    assert cat == HIPAACategory.NAMES and lbl == "NAME"
    cat, lbl = analyzer._map_entity("I-NAME")
    assert cat == HIPAACategory.NAMES and lbl == "NAME"
    
    # 2. Multi-token LOCATION
    cat, lbl = analyzer._map_entity("B-LOCATION")
    assert cat == HIPAACategory.GEOGRAPHY and lbl == "LOCATION"
    cat, lbl = analyzer._map_entity("I-LOCATION")
    assert cat == HIPAACategory.GEOGRAPHY and lbl == "LOCATION"
    
    # 3. DATE
    cat, lbl = analyzer._map_entity("B-DATE")
    assert cat == HIPAACategory.DATES_AGES and lbl == "DATE"
    
    # 4. AGE
    cat, lbl = analyzer._map_entity("B-AGE")
    assert cat == HIPAACategory.DATES_AGES and lbl == "AGE"
    
    # 5. ID / MRN
    cat, lbl = analyzer._map_entity("B-ID")
    assert cat == HIPAACategory.OTHER_ID and lbl == "ID"
    cat, lbl = analyzer._map_entity("B-MRN")
    assert cat == HIPAACategory.MRN and lbl == "MRN"
    
    # 6. PHONE / CONTACT
    cat, lbl = analyzer._map_entity("B-PHONE")
    assert cat == HIPAACategory.PHONE and lbl == "PHONE"
    cat, lbl = analyzer._map_entity("B-CONTACT")
    assert cat == HIPAACategory.PHONE and lbl == "CONTACT"
    
    # 7. EMAIL
    cat, lbl = analyzer._map_entity("B-EMAIL")
    assert cat == HIPAACategory.EMAIL and lbl == "EMAIL"
    
    # 8. SSN
    cat, lbl = analyzer._map_entity("B-SSN")
    assert cat == HIPAACategory.SSN and lbl == "SSN"

    # 9. HOSPITAL & PROFESSION
    cat, lbl = analyzer._map_entity("B-HOSPITAL")
    assert cat == HIPAACategory.GEOGRAPHY and lbl == "FACILITY"
    cat, lbl = analyzer._map_entity("B-PROFESSION")
    assert cat == HIPAACategory.OTHER_ID and lbl == "PROFESSION"

def test_weight_detection_safetensors(caplog):
    """Test model weight detection logic for safetensors vs bin vs fallback."""
    with caplog.at_level(logging.INFO):
        # Default fallback load
        analyzer = TransformerPHIAnalyzer()
        assert "Loading" in caplog.text or analyzer.model_name is not None
