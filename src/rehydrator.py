import os
import json
import base64
import re
from pathlib import Path
from typing import Dict, Tuple
from cryptography.fernet import Fernet
from src.regex_engine import RegexPHIAnalyzer

DEFAULT_KEY_FILE = Path(__file__).resolve().parent.parent / "data" / "key.bin"


def get_persistent_fernet_key() -> bytes:
    if "FERNET_SECRET_KEY" in os.environ:
        return os.environ["FERNET_SECRET_KEY"].encode("utf-8")
    if DEFAULT_KEY_FILE.exists():
        try:
            with open(DEFAULT_KEY_FILE, "rb") as f:
                return f.read().strip()
        except Exception:
            pass
    key = Fernet.generate_key()
    try:
        DEFAULT_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_KEY_FILE, "wb") as f:
            f.write(key)
    except Exception:
        pass
    return key


class Rehydrator:

    def __init__(self, secret_key: bytes = None):
        self.key = secret_key or get_persistent_fernet_key()
        self.cipher = Fernet(self.key)

    def encrypt_mapping(self, mapping: Dict[str, str]) -> str:
        return base64.b64encode(
            self.cipher.encrypt(json.dumps(mapping).encode("utf-8"))
        ).decode("utf-8")

    def decrypt_mapping(self, encrypted_token: str) -> Dict[str, str]:
        raw = base64.b64decode(encrypted_token.encode("utf-8"))
        return json.loads(self.cipher.decrypt(raw).decode("utf-8"))

    def rehydrate(self, response_text: str, encrypted_mapping: str,
                  use_shifted_dates: bool = False) -> Tuple[str, Dict]:
        mapping = self.decrypt_mapping(encrypted_mapping)
        result = response_text

        for pseudonym, val in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
            if pseudonym.endswith("_SHIFTED") or pseudonym == "_AGE_OVER_89_LIST":
                continue
            replacement = val
            if use_shifted_dates and f"{pseudonym}_SHIFTED" in mapping:
                replacement = mapping[f"{pseudonym}_SHIFTED"]
            result = result.replace(pseudonym, replacement)

        if "_AGE_OVER_89_LIST" in mapping:
            try:
                ages = json.loads(mapping["_AGE_OVER_89_LIST"])
                def _restore(match):
                    return ages.pop(0) if ages else match.group(0)
                result = re.sub(r'\b90\+(?!\w)', _restore, result)
            except Exception:
                pass

        residual = re.findall(r'\[[A-Z_]+_\d+\]', result)
        analyzer = RegexPHIAnalyzer()
        spans = analyzer.analyze(result)

        report = {
            "unmatched_tokens": residual,
            "detected_phi_count": len(spans),
            "status": "SECURE" if not residual else "WARNING",
        }
        return result, report
