"""Field extraction node — LLM primary, regex guardrail, merged output."""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMUnavailable, llm
from app.agent.nodes._base import traced
from app.agent.prompts import EXTRACTION_SYSTEM, extraction_user
from app.core.config import settings
from app.services import heuristics
from app.services.taxonomy import COMPLAINT_SOURCES, COMPLAINT_TYPES, DOSAGE_FORMS

FIELD_KEYS = (
    "complaint_source", "customer_name", "customer_contact", "customer_country",
    "product_name", "product_strength", "dosage_form", "batch_number",
    "manufacturing_date", "expiry_date", "quantity_affected", "quantity_unit",
    "market_country", "complaint_type", "complaint_date", "date_received",
    "description", "sample_available",
)

DATE_FIELDS = {"manufacturing_date", "expiry_date", "complaint_date", "date_received"}
ENUMS = {
    "complaint_source": COMPLAINT_SOURCES,
    "complaint_type": COMPLAINT_TYPES,
    "dosage_form": DOSAGE_FORMS,
}

# Identifier fields where a verbatim regex match is more trustworthy than a
# small model's transcription.
REGEX_PREFERRED = {"batch_number", "customer_contact", "quantity_affected"}


def _snap_to_enum(field: str, value: Any) -> Any:
    """Map a free-text model answer onto the controlled vocabulary."""
    options = ENUMS.get(field)
    if not options or not isinstance(value, str):
        return value
    lowered = value.strip().lower()
    for option in options:
        if option.lower() == lowered:
            return option
    for option in options:
        if lowered in option.lower() or option.lower() in lowered:
            return option
    # Token overlap as a last resort.
    tokens = set(lowered.replace("/", " ").split())
    best, best_score = None, 0
    for option in options:
        score = len(tokens & set(option.lower().replace("/", " ").split()))
        if score > best_score:
            best, best_score = option, score
    return best if best_score >= 1 else None


def _coerce(field: str, value: Any) -> Any:
    if value in (None, "", "null", "N/A", "n/a", "unknown", "Unknown", "not stated"):
        return None
    if field in DATE_FIELDS:
        parsed = heuristics.parse_date(str(value))
        return parsed.isoformat() if parsed else None
    if field == "quantity_affected":
        try:
            return float(str(value).replace(",", "").split()[0])
        except (ValueError, IndexError):
            return None
    if field == "sample_available":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "y", "available", "enclosed"}
    if field in ENUMS:
        return _snap_to_enum(field, value)
    return str(value).strip()[:1200]


def _normalise_llm_fields(payload: dict) -> dict[str, dict]:
    raw = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
    out: dict[str, dict] = {}
    for key in FIELD_KEYS:
        entry = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(entry, dict):
            value = _coerce(key, entry.get("value"))
            confidence = float(entry.get("confidence") or 0.0)
            evidence = entry.get("evidence")
        else:
            value = _coerce(key, entry)
            confidence = 0.6 if value is not None else 0.0
            evidence = None
        if value is None:
            confidence = 0.0
        out[key] = {
            "value": value,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "evidence": (str(evidence)[:140] if evidence else None),
            "source": "llm" if value is not None else "none",
        }
    return out


def _merge(llm_fields: dict[str, dict], regex_fields: dict[str, dict]) -> dict[str, dict]:
    """Merge the two engines, field by field, with an explicit policy."""
    merged: dict[str, dict] = {}
    for key in FIELD_KEYS:
        a = llm_fields.get(key) or {"value": None, "confidence": 0.0, "evidence": None, "source": "none"}
        b = regex_fields.get(key) or {"value": None, "confidence": 0.0, "evidence": None, "source": "none"}

        if a["value"] is None and b["value"] is None:
            merged[key] = {**a, "source": "none"}
            continue
        if a["value"] is None:
            merged[key] = b
            continue
        if b["value"] is None:
            merged[key] = a
            continue

        if key in REGEX_PREFERRED and b["confidence"] >= 0.8:
            # Both engines agree → boost; disagree → trust the literal match.
            agrees = str(a["value"]).strip().upper() == str(b["value"]).strip().upper()
            winner = dict(b)
            winner["confidence"] = min(1.0, b["confidence"] + (0.07 if agrees else -0.1))
            winner["source"] = "llm+regex" if agrees else "regex"
            merged[key] = winner
            continue

        merged[key] = a if a["confidence"] >= b["confidence"] else b

    return merged


@traced("extract")
def extract(state: dict, config: dict | None = None) -> dict[str, Any]:
    text = state.get("raw_text") or ""
    regex_fields = heuristics.extract_fields(text, state.get("channel", "document"))

    engine, model, note = "heuristic", None, None
    warnings: list[str] = []
    fields = regex_fields

    if llm.enabled:
        try:
            payload = llm.complete_json(
                system=EXTRACTION_SYSTEM,
                user=extraction_user(text),
                model=settings.extraction_model,
            )
            fields = _merge(_normalise_llm_fields(payload), regex_fields)
            engine, model = "groq", settings.extraction_model
        except LLMUnavailable as exc:
            note = f"Groq extraction unavailable, deterministic engine used ({exc})"
            warnings.append(
                "The language model could not be reached; fields were extracted with the "
                "rule-based engine. Review every value before saving."
            )
    else:
        note = "GROQ_API_KEY not configured — deterministic engine used."

    # Analyst-entered values always win over machine values.
    existing = state.get("existing_form") or {}
    for key, value in existing.items():
        if key in fields and value not in (None, "", []):
            fields[key] = {
                "value": value, "confidence": 1.0, "evidence": None, "source": "analyst",
            }

    populated = sum(1 for f in fields.values() if f["value"] not in (None, ""))
    mean_conf = (
        sum(f["confidence"] for f in fields.values() if f["value"] not in (None, "")) / populated
        if populated else 0.0
    )

    return {
        "fields": fields,
        "warnings": warnings,
        "engine": engine,
        "_meta": {
            "engine": engine,
            "model": model,
            "note": note,
            "digest": {
                "fields_populated": populated,
                "fields_total": len(FIELD_KEYS),
                "mean_confidence": round(mean_conf, 2),
            },
        },
    }
