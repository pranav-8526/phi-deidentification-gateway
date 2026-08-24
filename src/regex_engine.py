import re
from typing import List, Dict, Any
from src.config import HIPAACategory


class PHISpan:
    def __init__(self, start: int, end: int, label: str, text: str,
                 category: HIPAACategory, score: float = 1.0):
        self.start = start
        self.end = end
        self.label = label
        self.text = text
        self.category = category
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start, "end": self.end, "label": self.label,
            "text": self.text, "category": self.category.value, "score": self.score,
        }

    def __repr__(self):
        return f"<PHISpan {self.category.value} [{self.start}:{self.end}] '{self.text}'>"


class RegexPHIAnalyzer:
    PATTERNS = [
        (HIPAACategory.SSN, "SSN", re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b')),
        (HIPAACategory.EMAIL, "EMAIL", re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')),
        (HIPAACategory.PHONE, "PHONE", re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', re.IGNORECASE)),
        (HIPAACategory.FAX, "FAX", re.compile(r'\b(?:Fax|F|Fax Number)[:\s]*\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', re.IGNORECASE)),
        (HIPAACategory.IP, "IP_ADDRESS", re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')),
        (HIPAACategory.URL, "URL", re.compile(r'\bhttps?:\/\/[^\s/$.?#].[^\s]*\b', re.IGNORECASE)),
        (HIPAACategory.MRN, "MRN", re.compile(r'\b(?:PCG|MRN|Medical Record Number|ID)[:\s#]*[A-Z0-9-]{4,25}\b', re.IGNORECASE)),
        (HIPAACategory.HEALTH_PLAN, "HEALTH_PLAN", re.compile(r'\b(?:Policy|Plan|Member|Beneficiary|Group|Claim)[:\s#]*[A-Z0-9-]{4,25}\b', re.IGNORECASE)),
        (HIPAACategory.ACCOUNT, "ACCOUNT", re.compile(r'\b(?:Account|Acct)[:\s#]*[A-Z0-9-]{4,25}\b', re.IGNORECASE)),
        (HIPAACategory.CERTIFICATE, "LICENSE", re.compile(r'\b(?:License|Licence|NPI|DEA|Cert)[:\s#]*[A-Z0-9-]{4,25}\b', re.IGNORECASE)),
        (HIPAACategory.VEHICLE, "VEHICLE", re.compile(r'\b(?:VIN|License\s+Plate|Plate|Vehicle\s+ID|Tag)[:\s#]*[A-Z0-9-]{4,17}\b', re.IGNORECASE)),
        (HIPAACategory.VEHICLE, "LICENSE_PLATE", re.compile(r'\b[A-Z]{2,4}[-\s]?\d{3,4}\b')),
        (HIPAACategory.DEVICE, "DEVICE", re.compile(r'\b(?:UDI|Serial|Device)[:\s#]*[A-Z0-9-]{6,25}\b', re.IGNORECASE)),
        (HIPAACategory.OTHER_ID, "OTHER_ID", re.compile(r'\b(?:Other ID|Unique Code|ID Code)[:\s#]*[A-Z0-9-]{4,20}\b', re.IGNORECASE)),
        (HIPAACategory.GEOGRAPHY, "ZIPCODE", re.compile(r'\b\d{5}(?:-\d{4})?\b')),
        (HIPAACategory.GEOGRAPHY, "CITY_STATE", re.compile(
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s+(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b'
        )),
        (HIPAACategory.GEOGRAPHY, "FACILITY", re.compile(
            r'\b(?:[Ss]t\.\s*|[Ss]aint\s*|[Mm]ount\s*)?[A-Z\u00C0-\u00DE][A-Za-z0-9\u00C0-\u024F\'-]*(?:\s+(?:[A-Z\u00C0-\u00DE][A-Za-z0-9\u00C0-\u024F\'-]*|of|and|the))*\s+(?:[Hh]ospital|[Cc]linic|[Mm]edical\s+[Cc]enter|[Hh]ealth\s+[Cc]enter|[Ii]nfirmary|[Cc]are\s+[Cc]enter|[Ss]anatorium)\b'
        )),
        (HIPAACategory.NAMES, "NAME_BANNER", re.compile(r'\b[A-Z]{2,},\s+[A-Z .\-]{2,}\b')),
        (HIPAACategory.NAMES, "NAME_PREFIX", re.compile(
            r'\b(?:[Dd]r\.|[Dd]octor|[Mm]r\.|[Mm]rs\.|[Mm]s\.|[Pp]rof\.|[Pp]t\.?|[Pp]atient)\s+([A-Z\u00C0-\u00DE][A-Za-z\u00C0-\u024F\'-,]*(?:\s+[A-Z\u00C0-\u00DE][A-Za-z\u00C0-\u024F\'-,]*){0,2})\b'
        )),
        (HIPAACategory.NAMES, "NAME_FIELD", re.compile(
            r'\b(?:[Pp]atient\s+[Nn]ame|[Pp]rovider\s+[Nn]ame|[Pp]hysician\s+[Nn]ame|[Dd]octor\s+[Nn]ame|[Ee]mergency\s+[Cc]ontact|[Gg]uarantor|[Nn]ext\s+of\s+[Kk]in|[Aa]ttending|[Rr]eferring|[Ss]urgeon|[Nn]ickname|[Aa]lias|[Aa][Kk][Aa]|[Pp]atient:|[Pp]rovider:|[Pp]hysician:|[Dd]octor:|[Pp]t:)\s*:?\s*([A-Z\u00C0-\u00DE][A-Za-z\u00C0-\u024F\'-,]*(?:\s+[A-Z\u00C0-\u00DE][A-Za-z\u00C0-\u024F\'-,]*){0,3})\b'
        )),
        (HIPAACategory.DATES_AGES, "DATE", re.compile(
            r'\b(?:'
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|'
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|'
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]+\d{1,2},?[-.\s]+\d{4}|'
            r'\d{1,2}[-.\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-.\s]+\d{4}'
            r')\b', re.IGNORECASE
        )),
        (HIPAACategory.DATES_AGES, "YEAR", re.compile(
            r'\b(?:Born|DOB|Birth|Admitted|Discharged)[:\s#]*(\d{4})\b', re.IGNORECASE
        )),
    ]

    def analyze(self, text: str) -> List[PHISpan]:
        spans = []
        for category, label, pattern in self.PATTERNS:
            for m in pattern.finditer(text):
                if m.groups() and m.group(1):
                    start, end, val = m.start(1), m.end(1), m.group(1)
                else:
                    start, end, val = m.start(), m.end(), m.group(0)
                spans.append(PHISpan(start, end, label, val, category, score=1.0))
        return spans
