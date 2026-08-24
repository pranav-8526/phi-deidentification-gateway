# Approach Note: PHI/PII De-identification Gateway

## 1. Problem framing

Entity tagging alone does not solve this problem. Under-masking leaks PHI (a breach); over-masking destroys clinical meaning (a useless gateway). Both count as failure, and the brief says exactly that. Every design choice below therefore puts recall first, then recovers utility through consistent pseudonymisation and per-patient date shifting instead of blunt redaction.

## 2. Model

| | Choice |
|---|---|
| Primary | BioClinical-ModernBERT-base, 149M params (within the 1B limit), MIT licence, 8192-token context |
| Fallback | emilyalsentzer/Bio_ClinicalBERT (~110M) or microsoft/deberta-v3-base (~86M) |

Why this model: continued pre-training on 53.5B biomedical and clinical tokens across 20 datasets, and an 8192-token context that processes long clinical notes whole. That removes chunk-boundary span errors and the need for sliding-window merge logic. On identical evaluation setup it reports DEID F1 82.7 on the BLUE benchmark against 74.2 for Bio_ClinicalBERT (Sounack et al., arXiv:2506.10896). The task framing is BIO token classification with one label per HIPAA category. Exact parameter count will be reported from `model.num_parameters()`.

## 3. Data

1. Training: Technetium-I (HF `temlm-foundation/Technetium-I`), 498k synthetic clinical notes with 7.74M PHI spans across 10 entity types, mapped onto HIPAA categories, EUPL-1.2 licence. I will subsample roughly 50-100k notes and augment underrepresented categories with Faker plus templated generation (generator documented in the repo).
2. Day-1 action: register at the n2c2 DBMI Data Portal for the i2b2/n2c2 2014 de-id corpus. If the DUA clears before Day 7 I will add it as training and eval data for gold-standard comparability; if it does not, FAILURES.md will say so plainly.
3. Test set: at least 50 held-out notes, hand-annotated by me, deliberately adversarial. Built from the supplied Whitfield synthetic record (headers, signature blocks, conflicting duplicates, the transcribed illegible note), Faker-generated notes, and the open SHIELD sample.

## 4. Architecture

```
text ─► normalise ─► regex pass ─► NER pass ─► merge spans ─► date-shift engine ─► masked text
                     (deterministic) (model)     (union; longest      (per-patient offset)
                                                  span wins)                  │
                                                                       encrypted mapping ◄─┘
foundation LLM ◄── masked text          rehydrate(LLM_response, mapping) ─► final answer
```

- Service: FastAPI exposing exactly `deidentify(text) -> (masked_text, mapping)` and `rehydrate(response, mapping) -> text`, with a pluggable LLM adapter for the round-trip demo.
- Regex union model: regex guarantees well-formed patterns (SSN, phone, MRN, URL, IP, email) are never missed even when the model is unsure. The model carries the context-dependent entities: names, locations, institutional surnames.
- Masking strategy: consistent typed pseudonyms (`[NAME_1]`, `[ORG_1]`, `[CONTACT_1]` and similar), stable per original value within a patient. Pseudonymisation beats redaction because it preserves sentence structure and coreference, and beats surrogate generation because nothing gets invented. Lothritz et al. (NoDaLiDa 2023) found pseudonymisation matches or beats masking for downstream utility.

## 5. Dates and ages

All dates shift by one random offset per patient (-364 to +364 days, drawn once, stored in the mapping), so intervals like "3 days post-op" survive verbatim while calendar dates do not (SANT method, Hripcsak et al., JAMIA 2016). An optional day-of-week-preserving mode shifts in multiples of 7.

Relative dates ("two weeks ago") stay untouched; they carry no calendar PHI.

Ages over 89 follow 45 CFR §164.514(b)(2)(i)(C): any age above 89 becomes "90+", and shifted DOBs are capped so implied age never exceeds 89.

## 6. Evaluation (harness built Day 2-3, not Day 6)

Baselines: (a) regex-only, (b) stock Microsoft Presidio with spaCy lg, (c) Presidio strengthened with `obi/deid_roberta_i2b2`.

| Metric | Note |
|---|---|
| Entity-level P / R / F1 | Per HIPAA category plus micro/macro |
| Recall and leak rate | Leak rate = % documents with at least one missed identifier. This is the headline number, tuned via per-class thresholds (recall first for NAME / ID / CONTACT classes) |
| Utility preservation | Foundation LLM answers 10 QA pairs per note on original vs masked text; report agreement delta. Literature expectation is small, non-significant degradation (Vakili et al., LREC 2022), but I will measure it rather than assume it |
| Latency / throughput | p50 / p95, CPU and GPU |

Recall asymmetry is baked into training as well: class-weighted loss weights false negatives above false positives, and low-confidence spans route to a review queue instead of being written silently.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| n2c2 DUA not granted within a week | Technetium-I is primary from Day 1; n2c2 is additive only |
| Model trained on synthetic data misses real-world distribution | Hand-labelled test set includes realistic adversarial cases (Whitfield record style); negative results reported honestly |
| Eponym ambiguity ("Dr. Parkinson diagnosed Parkinson's") cannot be solved by rules | The model learns context; residual cases are accepted, documented, and caught by the review queue when confidence is low |
| Over-redaction harms downstream utility | Measured directly via the QA delta; pseudonymisation was chosen partly for this reason |

## 8. Timeline (fits the brief)

D0-D1 skeleton end-to-end with stubs; D1-D3 data pipeline, eval harness, baselines; D3-D5 fine-tune and threshold tuning; D5-D6 iterate on the weakest link guided by harness numbers; D6-D7 repo polish, FAILURES.md written throughout, demo video, live round-trip script rehearsed on an unseen note.

---

# Annex A: edge-case handling matrix

| # | Edge case | Handling |
|---|---|---|
| 1 | Eponym ambiguity: "Dr. Parkinson diagnosed Parkinson's", "Mr. Wood admitted to Wood Memorial"; drug and instrument eponyms (Foley, Babinski, Lasix tagged PERSON by general NER) | Contextual disambiguation is the model's job, which is why we train instead of writing rules; a clinical-vocabulary whitelist (drugs, procedures, syndromes) suppresses regex false PERSON hits; residual errors reported |
| 2 | Institutions containing surnames ("Hollings Cancer Center", "Wood Memorial Hospital") | ORG label trained explicitly (Technetium-I has a HOSPITAL type); org spans win the merge over person spans when followed by institution nouns |
| 3 | Names that are common words or months ("May", "Mai", "Winter"); documented miss rates of 18-23% in existing tools | Training data includes word-names; capitalisation-in-context features; conservative recall-first threshold for NAME |
| 4 | Hyphenated or apostrophe names half-redacted ("O'Brien-Nakamura"); ALL-CAPS template names ("JACKSON") | Augmentation set explicitly contains hyphenated, apostrophised, accented, and all-caps variants; label smoothing across subtoken boundaries; span merging across adjacent B-/I- tags |
| 5 | Provider vs patient name confusion (both are PHI, both must go, but they play different roles) | Both masked regardless; distinct token types ([NAME] vs [PROVIDER]) preserve role semantics for the downstream LLM where distinguishable |
| 6 | Date shifting destroying intervals | Never remove dates; shift them consistently per patient (section 5). Intervals and day-counts survive exactly |
| 7 | Mixed date formats (02/11/2024 ambiguous between dd/mm and mm/dd; the "17/02/2024" trap) | Normaliser detects each document's format convention from unambiguous anchors before parsing; ambiguous-only dates shifted conservatively; parse failures treated as DATE spans (mask rather than mis-shift) |
| 8 | Ages over 89 | Cap rule in section 5; ages up to 89 preserved because they are clinically meaningful and Safe Harbor-compliant |
| 9 | Identifiers hiding in headers, footers, signature blocks, and table cells (every page of a fax dump repeats the patient banner) | No document-region exemption: full-text scanning including headers; repeated banner spans deduplicated at the mapping level, not skipped at detection; table cells scanned line-wise |
| 10 | Misspelled or OCR-noisy identifiers ("Smth, John") | Character-level noise augmentation during fine-tuning; fuzzy regex patterns for IDs; recall-first thresholds absorb residual noise |
| 11 | Small geographies (Safe Harbor requires masking below state level), partial addresses, "St. Mary's in Springfield" | LOC/GPE/FAC labels plus address regexes; state-level and above left intact since Safe Harbor permits state |
| 12 | Phone, fax, email, SSN, MRN, account numbers, device IDs, URLs, IPs, licence plates | Regex layer guarantees these deterministic formats at near-100% recall; model covers free-form variants; MRN/account patterns configurable per deployment schema |
| 13 | Categories absent from free text (photos, biometrics, categories 16 and 17) | Out of scope for a text gateway; stated in the coverage table with justification, as the brief invites |
| 14 | Recall asymmetry (a false negative is a breach, a false positive is an inconvenience) | Weighted loss; threshold sweep maximising recall at a precision floor; leak rate reported as the headline metric |
| 15 | Mapping security: where does the mapping live? | Server-side only, Fernet-encrypted at rest, keyed by an ephemeral session ID with TTL; never transmitted to the LLM; unit-tested so that no plaintext identifier appears in anything sent outbound |
| 16 | LLM echoes a token that was never in the input ("[NAME_99]") | Rehydrater substitutes known tokens only; unknown tokens pass through untouched with a logged warning; a final safety scan runs SSN/phone-shaped regexes over the response |
| 17 | Duplicate or conflicting mentions across documents ("Whitfield" vs "Whitmore" pages) | Same-value maps to same-pseudonym via value hash; conflicting name/DOB variants each masked; cross-document identity conflicts flagged for review rather than silently merged |
| 18 | Demographic fairness (documented recall variance by name origin across systems) | Test set intentionally spans name origins; per-group recall spot-check reported in FAILURES.md |
| 19 | Very long notes (>512 tokens) | The 8192-token context removes chunking entirely; fallback models use stride-window overlap with span reconciliation |
| 20 | Non-determinism and hallucination | An encoder-only architecture is fully deterministic given fixed weights, so there is no generative masking; the brief's hallucination clause is addressed by design |

# Annex B: HIPAA Safe Harbor coverage statement (18 categories)

| Covered in text gateway | Categories |
|---|---|
| Yes, model plus regex | 1 Names; 2 Geo below state; 3 Dates (shifted) plus ages over 89; 4 Phone; 5 Fax; 6 Email; 7 SSN; 8 MRN; 9 Health-plan numbers; 10 Account numbers; 11 Certificate/licence numbers; 12 Vehicle/plate; 13 Device IDs/serials; 14 URLs; 15 IPs; 18 Other unique IDs/codes |
| N/A, not textual | 16 Biometric identifiers; 17 Full-face photos (gateway processes text only; stated with justification as the brief invites) |

Sources: Sounack et al. 2025 (arXiv:2506.10896); Alsentzer et al. 2019; Stubbs & Uzuner 2015 (i2b2 2014 overview, top system entity-F1 0.936); Hripcsak et al., JAMIA 2016 (SANT); Lothritz et al., NoDaLiDa 2023; Vakili et al., LREC 2022; HHS de-identification guidance (45 CFR §164.514(b)); Presidio supported-entity docs; Lucairn clinical-deid benchmark 2026.
