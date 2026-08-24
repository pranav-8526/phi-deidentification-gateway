import re
import hmac
import hashlib
from datetime import datetime, timedelta


class DateShifter:

    def __init__(self, seed: int = None, preserve_weekday: bool = False):
        if seed is not None:
            h = hmac.new(b"PHI_GATEWAY_HMAC_SECRET", str(seed).encode(), hashlib.sha256).digest()
            offset = (int.from_bytes(h[:4], "big") % 729) - 364
        else:
            offset = 180

        if preserve_weekday:
            offset = (offset // 7) * 7

        self.offset_days = offset if offset != 0 else 14

    def shift_date_str(self, date_str: str) -> str:
        clean = date_str.strip()
        parts = re.split(r'[-/.]', clean)
        if len(parts) == 3 and parts[0].isdigit() and int(parts[0]) > 12:
            formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"]
        else:
            formats = [
                "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y",
                "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
            ]
        for fmt in formats:
            try:
                dt = datetime.strptime(clean, fmt)
                return (dt + timedelta(days=self.offset_days)).strftime(fmt)
            except ValueError:
                continue
        return clean


# Words that precede numbers but do not indicate a patient age.
_NON_AGE_CONTEXT = [
    "paragraph", "page", "table", "figure", "section", "no", "room", "suite",
    "temp", "bp", "hr", "pulse", "weight", "date", "year", "id", "code", "val",
    "value", "level", "serial", "sn", "vin", "plate", "claim", "policy", "fax", "phone",
]

_AGE_PATTERN = re.compile(
    r'(\b(?:age\s*:?\s*|aged\s+)?)\b(8[9]|9[0-9]|1[0-1][0-9])\b(\s*(?:years?\s*old|y/o|-year-old)?\b)',
    re.IGNORECASE,
)


class AgeCapper:

    @staticmethod
    def cap_ages_in_text(text: str) -> str:
        def _replace(match):
            prefix = match.group(1) or ""
            num_str = match.group(2)
            suffix = match.group(3) or ""
            start = match.start(2)
            left = text[max(0, start - 25):start].strip().lower()
            right = text[start + len(num_str):min(len(text), start + len(num_str) + 25)].strip().lower()

            if left.endswith("-"):
                return match.group(0)
            if right.startswith("-") and not right.startswith("-year"):
                return match.group(0)
            if any(w in left for w in _NON_AGE_CONTEXT):
                return match.group(0)

            try:
                if int(num_str) > 89:
                    return f"{prefix}90+{suffix}"
            except ValueError:
                pass
            return match.group(0)

        return _AGE_PATTERN.sub(_replace, text)
