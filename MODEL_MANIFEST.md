# MODEL MANIFEST — BIO-CLINICAL MODERNBERT PHI NER ADAPTER

---

## 1. Model Identification
* **Model Name:** BioClinical-ModernBERT-base-41label-PHI
* **Base Architecture:** `thomas-sounack/BioClinical-ModernBERT-base` (`ModernBertForTokenClassification`)
* **Task:** Clinical Named Entity Recognition (Token Classification)
* **Local Adapter Path:** `models/adapter/`
* **Primary Model File:** `models/adapter/model.safetensors` (~448.8 MB)
* **Parameter Count:** `149,633,317`
* **Precision:** `float32` / `fp16`

---

## 2. Dataset & Training Specifications
* **Dataset:** `temlm-foundation/Technetium-I`
* **Training Sample Size:** 50,000 anonymized clinical notes
* **Train / Validation Split:** 90% Train (45,000 notes) / 10% Validation (5,000 notes)
* **Epochs:** `3`
* **Batch Size:** `16` per device
* **Optimizer:** AdamW (`lr=2e-5`)
* **Loss Function:** Weighted Cross-Entropy (Weight = 3.0 for all entity classes, Weight = 1.0 for Class 0 `O`)
* **Tokenization:** Offset mapping subword alignment with `-100` ignore index for special tokens.

---

## 3. Label Scheme (41 BIO Classes)
```json
{
  "0": "O",
  "1": "B-NAME", "2": "I-NAME",
  "3": "B-DATE", "4": "I-DATE",
  "5": "B-LOCATION", "6": "I-LOCATION",
  "7": "B-AGE", "8": "I-AGE",
  "9": "B-ID", "10": "I-ID",
  "11": "B-CONTACT", "12": "I-CONTACT",
  "13": "B-PHONE", "14": "I-PHONE",
  "15": "B-EMAIL", "16": "I-EMAIL",
  "17": "B-SSN", "18": "I-SSN",
  "19": "B-MRN", "20": "I-MRN",
  "21": "B-ACCOUNT", "22": "I-ACCOUNT",
  "23": "B-DEVICE", "24": "I-DEVICE",
  "25": "B-VEHICLE", "26": "I-VEHICLE",
  "27": "B-URL", "28": "I-URL",
  "29": "B-IP", "30": "I-IP",
  "31": "B-HEALTH_PLAN", "32": "I-HEALTH_PLAN",
  "33": "B-CERTIFICATE", "34": "I-CERTIFICATE",
  "35": "B-OTHER_ID", "36": "I-OTHER_ID",
  "37": "B-HOSPITAL", "38": "I-HOSPITAL",
  "39": "B-PROFESSION", "40": "I-PROFESSION"
}
```

---

## 4. Reproducible Training & Execution Commands

### Execution on GPU (Google Colab / Kaggle / Cloud Instance)
```bash
python scripts/train_bio_clinical_ner.py
```

### Diagnostic Audit Command
```bash
python src/ner_model.py
```

---

## 5. Artifact Verification & Checksum Information
* **`config.json`:** Defines 41 BIO `id2label` mapping and token classification head structure.
* **`adapter_config.json`:** Model metadata and training arguments.
* **`model.safetensors`:** Fine-tuned token classification weights (~448.8 MB). Generated upon running training script.
