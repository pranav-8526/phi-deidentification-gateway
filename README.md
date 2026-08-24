# PHI / PII De-identification Gateway

A production-ready, high-performance, HIPAA-compliant de-identification gateway designed to securely sanitize clinical texts and medical documents before sending them to downstream Large Language Models (LLMs).

---

## 📌 Features

1. **18 HIPAA Safe Harbor Identifier Redaction**: Automatically detects and redacts identifiers (SSNs, names, phone numbers, email addresses, MRNs, IP addresses, dates, locations, and more).
2. **HMAC-Seeded Date Shifting**: Relative, patient-specific date shifting (within a range of ±364 days) preserving temporal relationships and order of events, while satisfying HIPAA requirements.
3. **HIPAA Age Capping Rule**: Detects and aggregates ages above 89, replacing them with a standardized `[AGE: 90+]` format.
4. **Context-Aware Eponym Protection**: Intelligent context window analysis to prevent false-positive redaction of medical conditions named after individuals (e.g. "Parkinson's disease", "Foley catheter") while still redacting patient and provider names.
5. **Lossless Encrypted Rehydration**: Uses symmetric AES-128 Fernet tokens to securely lock and decrypt the original patient data, allowing LLMs to summarize or analyze clean clinical notes and safely map the results back to the original patient.
6. **Obsidian-inspired Dark UI Studio**: Interactive side-by-side live editor with single-click sample loading, PDF upload capability, and instant parsing.

---

## 🛠️ Repository Structure

```
phi-deidentification-gateway/
├── APPROACH_NOTE.md       # Architecture approach & details (Day 2 deliverable)
├── FAILURES.md            # Diagnostic log & failure modes (Graded deliverable)
├── README.md              # Project documentation
├── requirements.txt       # Project package dependencies
├── src/
│   ├── api.py             # FastAPI REST API endpoints
│   ├── config.py          # HIPAA 18 Safe Harbor category definitions
│   ├── date_shifter.py    # HMAC date shifter & age capper
│   ├── eponym_whitelist.py# Eponym whitelist & disambiguation engine
│   ├── eval_harness.py    # Accuracy, recall, and latency benchmark evaluator
│   ├── gateway.py         # Gateway client exposing deidentify & rehydrate APIs
│   ├── hybrid_analyzer.py # Priority-based ensemble (Regex + Transformer NER)
│   ├── ner_model.py       # spaCy and BioClinical-ModernBERT entity classifier
│   ├── pseudonymizer.py   # Core pseudonym masking logic
│   └── rehydrator.py      # Session encryption & rehydration manager
├── tests/
│   ├── test_extended_cases.py # Edge cases & leakage validation
│   ├── test_gateway.py        # Gateway core component tests
│   └── test_hybrid.py         # Ensemble and eponym verification
├── scripts/
│   ├── baseline_presidio.py   # MS Presidio baseline benchmark script
│   ├── baseline_regex.py      # Regex-only baseline benchmark script
│   ├── demo_roundtrip.py      # End-to-end roundtrip demonstration script
│   ├── generate_synthetic_notes.py # Synthetic medical record notes generator
│   └── train_bio_clinical_ner.py # ModernBERT fine-tuning pipeline script
└── data/
    ├── samples/           # Sample clinical texts for local testing
    ├── eval/              # Gold evaluation dataset
    └── key.bin            # Persisted encryption key (auto-generated)
```

---

## 🚀 Quick Start & Usage

### 1. Install Dependencies
Make sure you have Python installed, then run:
```bash
pip install -r requirements.txt
```

### 2. Run Automated Test Suite
Verify system integrity and zero-leakage performance:
```bash
python -m pytest
```

### 3. Run End-to-End Command-Line Demo
Run the CLI demonstration script to visualize the full de-identification and rehydration pipeline:
```bash
python scripts/demo_roundtrip.py
```

### 4. Launch FastAPI REST Server & Web UI
Start the local REST server:
```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8080
```
- Open your browser and navigate to `http://127.0.0.1:8080/` to use the interactive Web UI Studio.
- Access the interactive OpenAPI docs at `http://127.0.0.1:8080/docs`.

---

## 📊 API Specification

### `POST /deidentify`
* **Input**:
```json
{
  "text": "Patient John Doe (SSN: 999-88-7777) admitted on 2024-02-11.",
  "patient_seed": 42
}
```
* **Output**:
```json
{
  "masked_text": "Patient [NAME_1] (SSN: [SSN_1]) admitted on [DATE_1].",
  "encrypted_mapping": "gAAAAABqiHmRV_djfk893rCH3HZeXBX8U98AeXyJILohe..."
}
```

### `POST /rehydrate`
* **Input**:
```json
{
  "llm_response": "Summary: Patient [NAME_1] (SSN: [SSN_1]) admitted on [DATE_1].",
  "encrypted_mapping": "gAAAAABqiHmRV_djfk893rCH3HZeXBX8U98AeXyJILohe..."
}
```
* **Output**:
```json
{
  "restored_text": "Summary: Patient John Doe (SSN: 999-88-7777) admitted on 2024-02-11."
}
```
