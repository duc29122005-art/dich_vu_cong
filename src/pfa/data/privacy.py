"""Candidate PII screening, never a guarantee of anonymity."""

import re
from collections import Counter
from dataclasses import dataclass

from pfa.data.preprocessing import normalize_text

PATTERNS = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE),
    "citizen_id": re.compile(r"(?<!\d)(?:\d[ .-]?){11}\d(?!\d)"),
    "phone": re.compile(r"(?<!\w)(?:\+84|0084|0)(?:[ .()-]?\d){8,10}(?!\w)"),
    "personal_identifier": re.compile(
        r"(?P<context>\b(?:CCCD|CMND|MST|mã số thuế|hộ chiếu|passport|số tài khoản|STK)"
        r"\s*[:#-]?\s*)[A-Z]{0,2}\d(?:[ .-]?\d){5,18}(?!\d)",
        re.IGNORECASE,
    ),
    "address": re.compile(
        r"\b(?:địa chỉ|đ/c)\s*[:：]|\b(?:số|số)\s+\d+[A-Za-z]?\s+(?:đường|phố|ngõ|hẻm)\b",
        re.IGNORECASE,
    ),
    "personal_name": re.compile(
        r"\b(?:họ và tên|họ tên|tên người phản ánh)\s*[:：]", re.IGNORECASE
    ),
}
AUDIT_VERSION = "privacy-audit-1"
CASE_NUMBER = re.compile(
    r"(?P<context>\b(?:mã hồ sơ|số hồ sơ|mã vụ việc|số vụ án|case id|ticket)\s*[:#-]?\s*)"
    r"(?:[A-Z]{1,8}[-/]?)?\d{5,20}(?!\w)|\b(?:PAKN|HS|CASE|TICKET)[-/]?\d{5,20}\b",
    re.IGNORECASE,
)
SENSITIVE_CONTEXT = re.compile(
    r"\b(?:bệnh án|chẩn đoán|HIV|số dư tài khoản|nạn nhân|bạo lực|trẻ em)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class Screening:
    text: str
    counts: dict[str, int]
    ambiguous: bool


def screen(text: str, categories: list[str] | None = None, max_length: int = 20000) -> Screening:
    """Redact candidate structured identifiers; flag free-form names/addresses."""
    text = normalize_text(text, max_length)
    counts: Counter = Counter()
    enabled = set(categories if categories is not None else PATTERNS)
    priority = ("email", "citizen_id", "personal_identifier", "phone", "address", "personal_name")
    for category in priority:
        if category not in enabled:
            continue
        pattern = PATTERNS[category]
        if category in {"address", "personal_name"}:
            counts[category] += len(pattern.findall(text))
        else:
            placeholder = f"[REDACTED_{category.upper()}]"
            if category == "personal_identifier":
                text, count = pattern.subn(lambda match: match.group("context") + placeholder, text)
            else:
                text, count = pattern.subn(placeholder, text)
            counts[category] += count
    return Screening(
        text,
        {name: count for name, count in counts.items() if count},
        bool(counts["address"] or counts["personal_name"]),
    )


def audit_screen(text: str, max_length: int = 20000) -> Screening:
    """Extend screening for audit without changing STEP 04's published contract."""
    text = normalize_text(text, max_length)
    text, cases = CASE_NUMBER.subn(
        lambda match: (match.group("context") or "") + "[REDACTED_CASE_NUMBER]", text
    )
    base = screen(text, max_length=max_length)
    counts = base.counts.copy()
    sensitive = len(SENSITIVE_CONTEXT.findall(base.text))
    if cases:
        counts["case_number"] = cases
    if sensitive:
        counts["sensitive_context"] = sensitive
    return Screening(base.text, counts, bool(base.ambiguous or cases or sensitive))
