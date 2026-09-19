"""Completeness checker.

Scores the draft record against what 21 CFR 211.198(a) and EU GMP Chapter 8
require before a complaint can move out of triage, then asks the model to turn
the gaps into questions the analyst can send to the complainant verbatim.
"""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMUnavailable, llm
from app.agent.nodes._base import traced
from app.agent.prompts import GAP_SYSTEM
from app.core.config import settings

# field, label, severity, weight, why it matters
REQUIREMENTS: list[tuple[str, str, str, float, str]] = [
    ("product_name", "Product Name", "blocker", 0.16,
     "21 CFR 211.198(a) requires the drug product name on every complaint record."),
    ("batch_number", "Batch / Lot Number", "blocker", 0.16,
     "Without the lot number the batch record cannot be retrieved and no investigation can start."),
    ("complaint_type", "Complaint Type", "blocker", 0.12,
     "The nature of the complaint drives classification and investigation route."),
    ("description", "Detailed Complaint Description", "blocker", 0.12,
     "A factual description of the defect is the evidentiary core of the record."),
    ("customer_name", "Customer Name", "required", 0.09,
     "The complainant must be identifiable to close the loop with a written reply."),
    ("complaint_source", "Complaint Source", "required", 0.06,
     "Channel of receipt determines acknowledgement timelines."),
    ("product_strength", "Product Strength / Grade", "required", 0.07,
     "Strength distinguishes presentations sharing a brand name."),
    ("expiry_date", "Expiry Date", "required", 0.07,
     "Expiry drives record retention and market-exposure assessment."),
    ("complaint_date", "Complaint Date", "required", 0.05,
     "Receipt date starts the regulatory clock for investigation turnaround."),
    ("quantity_affected", "Quantity Affected", "recommended", 0.04,
     "Quantity scopes the potential market exposure."),
    ("manufacturing_date", "Manufacturing Date", "recommended", 0.03,
     "Needed to correlate with campaign and equipment history."),
    ("sample_available", "Sample Availability", "recommended", 0.03,
     "Comparative testing against the retained sample depends on it."),
]

QUESTION_TEMPLATES = {
    "batch_number": "Could you share the batch or lot number printed on the pack?",
    "expiry_date": "What expiry date is printed on the affected pack?",
    "manufacturing_date": "What manufacturing date is printed on the pack?",
    "product_strength": "Which strength or grade of the product is affected?",
    "quantity_affected": "How many units are affected, and how many remain in your stock?",
    "sample_available": "Is the affected unit still available so we can arrange collection for testing?",
    "customer_name": "Could you confirm the name and organisation of the person reporting this?",
    "complaint_date": "On what date was the issue first observed?",
    "product_name": "Which product is affected — please confirm the full name as printed on the pack?",
    "description": "Could you describe what was observed in more detail, including where and when?",
}


def _present(fields: dict, key: str) -> bool:
    entry = fields.get(key) or {}
    value = entry.get("value")
    return value not in (None, "", [], {})


@traced("completeness")
def completeness(state: dict, config: dict | None = None) -> dict[str, Any]:
    fields = state.get("fields") or {}

    earned, gaps = 0.0, []
    for key, label, severity, weight, reason in REQUIREMENTS:
        if _present(fields, key):
            earned += weight
            continue
        gaps.append(
            {
                "field": key,
                "label": label,
                "severity": severity,
                "reason": reason,
                "suggested_question": QUESTION_TEMPLATES.get(key),
            }
        )

    total_weight = sum(r[3] for r in REQUIREMENTS)
    score = round(100.0 * earned / total_weight, 1)

    # Low-confidence values count as "present but shaky" — surface them too.
    shaky = [
        key for key, _l, _s, _w, _r in REQUIREMENTS
        if _present(fields, key) and (fields[key].get("confidence") or 0) < 0.45
    ]

    questions: list[str] = []
    engine, model, note = "deterministic", None, None
    if gaps and llm.enabled:
        record = {
            k: (fields.get(k) or {}).get("value") for k, *_ in
            [(r[0],) for r in REQUIREMENTS]
        }
        try:
            payload = llm.complete_json(
                system=GAP_SYSTEM,
                user=(
                    f"CURRENT RECORD (nulls are missing):\n{record}\n\n"
                    f"MISSING FIELDS: {[g['label'] for g in gaps]}\n\n"
                    "Write the clarifying questions."
                ),
                model=settings.extraction_model,
            )
            raw = payload.get("questions") or []
            questions = [str(q).strip() for q in raw if str(q).strip()][:4]
            engine, model = "groq", settings.extraction_model
        except LLMUnavailable as exc:
            note = f"Template questions used ({exc})"

    if not questions:
        questions = [
            QUESTION_TEMPLATES[g["field"]] for g in gaps if g["field"] in QUESTION_TEMPLATES
        ][:4]

    return {
        "completeness_score": score,
        "gaps": gaps,
        "clarifying_questions": questions,
        "_meta": {
            "engine": engine,
            "model": model,
            "note": note,
            "digest": {
                "score": score,
                "missing": len(gaps),
                "blockers": sum(1 for g in gaps if g["severity"] == "blocker"),
                "low_confidence_fields": shaky,
            },
        },
    }
