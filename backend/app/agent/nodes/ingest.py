from __future__ import annotations

import re
from typing import Any

from app.agent.nodes._base import traced
from app.services.documents import normalise

_SIGNAL_TOKENS = (
    "batch", "lot", "product", "complaint", "defect", "expiry", "mfg", "tablet",
    "capsule", "vial", "strip", "bottle", "pack",
)


@traced("ingest")
def ingest(state: dict, config: dict | None = None) -> dict[str, Any]:
    """Normalise the raw input and decide whether it is worth reasoning over."""
    text = normalise(state.get("raw_text") or "")
    warnings: list[str] = []

    word_count = len(text.split())
    signal_hits = sum(1 for token in _SIGNAL_TOKENS if token in text.lower())
    has_structure = bool(re.search(r"^\s*\w[\w \-/]{2,30}\s*:", text, re.MULTILINE))

    usable = word_count >= 12
    if not usable:
        warnings.append(
            "The supplied text is too short to extract a complaint record from. "
            "Paste the full complaint e-mail or upload the source document."
        )
    elif signal_hits == 0:
        warnings.append(
            "No pharmaceutical complaint vocabulary was detected — extraction "
            "confidence will be low. Verify this is the correct document."
        )

    document = {
        "usable": usable,
        "word_count": word_count,
        "char_count": len(text),
        "signal_hits": signal_hits,
        "structured": has_structure,
    }

    return {
        "document": document,
        "raw_text": text,
        "warnings": warnings,
        "_meta": {
            "engine": "deterministic",
            "digest": document,
            "note": None if usable else "Input rejected as unusable.",
        },
    }
