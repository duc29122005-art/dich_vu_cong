"""Conservative Unicode normalization; no accent, negation, or punctuation removal."""

import re
import unicodedata

TRANSFORMATION_VERSION = "conservative-1"


def normalize_text(text: str, max_length: int = 20000) -> str:
    """Remove unsafe controls, preserve Vietnamese, and enforce content bounds."""
    return transform_text(text, max_length)[0]


def transform_text(
    text: str,
    max_length: int = 20000,
    *,
    unicode_nfc: bool = True,
    whitespace: bool = True,
    controls: bool = True,
) -> tuple[str, dict[str, int]]:
    """Apply versioned conservative operations and return counts, never examples."""
    if len(text) > max_length:
        raise ValueError("Text exceeds configured maximum length")
    text.encode("utf-8")  # Reject lone surrogates before removing control characters.
    changes = {}
    if unicode_nfc:
        result = unicodedata.normalize("NFC", text)
        if result != text:
            changes["unicode_nfc"] = 1
        text = result
    if controls:
        result = "".join(
            char
            for char in text
            if char.isspace() or unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
        )
        if result != text:
            changes["controls_removed"] = len(text) - len(result)
        text = result
    if whitespace:
        result = re.sub(r"\s+", " ", text).strip()
        if result != text:
            changes["whitespace"] = 1
        text = result
    if not text.strip():
        raise ValueError("Text is empty after normalization")
    text.encode("utf-8")
    return text, changes
