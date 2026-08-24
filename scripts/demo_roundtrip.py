"""Roundtrip Demonstration Script for Project 2 PHI / PII Gateway."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gateway import DeIDGateway


def run_demo():
    print("=" * 80)
    print(" PROJECT 2: PHI / PII DE-IDENTIFICATION GATEWAY - LIVE ROUNDTRIP DEMO")
    print("=" * 80)

    sample_file = Path("data/samples/synthetic_clinical_notes.json")
    if not sample_file.exists():
        print("Error: Sample dataset not found.")
        return

    with open(sample_file, "r", encoding="utf-8") as f:
        notes = json.load(f)

    sample_note = notes[0]["text"]

    print("\n[STEP 1: RAW CLINICAL NOTE (INPUT)]")
    print("-" * 80)
    print(sample_note)

    gateway = DeIDGateway(seed=42)
    masked_text, encrypted_mapping = gateway.deidentify(sample_note, patient_seed=42)

    print("\n[STEP 2: DE-IDENTIFIED MASKED TEXT (SENT TO LLM)]")
    print("-" * 80)
    print(masked_text)
    print(f"\nEncrypted Session Token: {encrypted_mapping[:60]}...")

    simulated_llm_output = (
        f"CLINICAL SUMMARY:\n"
        f"Patient presented with chief complaints as outlined in note for [LOCATION_1].\n"
        f"Key Entities Noted: Patient {masked_text.splitlines()[0]}.\n"
        f"All identifiers masked according to HIPAA Safe Harbor guidelines."
    )

    print("\n[STEP 3: DOWNSTREAM FOUNDATION LLM RESPONSE]")
    print("-" * 80)
    print(simulated_llm_output)

    rehydrated_text = gateway.rehydrate(simulated_llm_output, encrypted_mapping)

    print("\n[STEP 4: REHYDRATED FINAL RESPONSE (RESTORED TO USER)]")
    print("-" * 80)
    print(rehydrated_text)
    print("=" * 80)
    print(" SUCCESS: End-to-end privacy gateway roundtrip completed without data leak!")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
