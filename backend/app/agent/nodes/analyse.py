"""Root cause + CAPA + executive summary."""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMUnavailable, llm
from app.agent.nodes._base import traced
from app.agent.prompts import ANALYSIS_SYSTEM
from app.core.config import settings
from app.services import heuristics
from app.services.taxonomy import ROOT_CAUSE_CATEGORIES

VALID_CAPA_TYPES = {"correction", "corrective", "preventive"}


def _clean_root_causes(raw: Any) -> list[dict]:
    out: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("hypothesis"):
            continue
        category = str(item.get("category") or "").strip()
        if category not in ROOT_CAUSE_CATEGORIES:
            match = next(
                (c for c in ROOT_CAUSE_CATEGORIES if c.split("—")[0].strip().lower() in category.lower()),
                None,
            )
            category = match or "Not Attributable — Insufficient Evidence"
        try:
            likelihood = max(0.0, min(1.0, float(item.get("likelihood") or 0)))
        except (TypeError, ValueError):
            likelihood = 0.0
        out.append(
            {
                "category": category,
                "hypothesis": str(item["hypothesis"])[:400],
                "likelihood": round(likelihood, 2),
                "investigation_step": (str(item.get("investigation_step"))[:300]
                                       if item.get("investigation_step") else None),
            }
        )
    return sorted(out, key=lambda r: r["likelihood"], reverse=True)[:4]


def _clean_capa(raw: Any) -> list[dict]:
    out: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("action"):
            continue
        capa_type = str(item.get("type") or "corrective").lower().strip()
        if capa_type not in VALID_CAPA_TYPES:
            capa_type = "corrective"
        try:
            due = int(item.get("due_in_days") or 0) or None
        except (TypeError, ValueError):
            due = None
        out.append(
            {
                "type": capa_type,
                "action": str(item["action"])[:500],
                "owner_function": (str(item.get("owner_function"))[:80]
                                   if item.get("owner_function") else "Quality Assurance"),
                "due_in_days": due,
                "effectiveness_check": (str(item.get("effectiveness_check"))[:300]
                                        if item.get("effectiveness_check") else None),
            }
        )
    order = {"correction": 0, "corrective": 1, "preventive": 2}
    return sorted(out, key=lambda c: order[c["type"]])[:5]


@traced("analyse")
def analyse(state: dict, config: dict | None = None) -> dict[str, Any]:
    fields = state.get("fields") or {}
    form = {k: (v or {}).get("value") for k, v in fields.items()}
    risk = state.get("risk") or {}
    severity = risk.get("severity") or "Minor"
    defect = form.get("complaint_type")

    root_causes = heuristics.fallback_root_causes(defect, severity)
    capa = heuristics.fallback_capa(defect, severity)
    summary = heuristics.fallback_summary({**form, "severity": severity})

    engine, model, note = "heuristic", None, None

    if llm.enabled:
        try:
            payload = llm.complete_json(
                system=ANALYSIS_SYSTEM,
                user=(
                    "CLASSIFIED COMPLAINT\n"
                    f"Product: {form.get('product_name')} {form.get('product_strength') or ''} "
                    f"({form.get('dosage_form') or 'dosage form not stated'})\n"
                    f"Batch: {form.get('batch_number')}  Mfg: {form.get('manufacturing_date')}  "
                    f"Exp: {form.get('expiry_date')}\n"
                    f"Defect: {defect}\n"
                    f"Severity: {severity}  Risk score: {risk.get('score')} ({risk.get('band')})\n"
                    f"Regulatory flags: {risk.get('regulatory_flags')}\n"
                    f"Quantity affected: {form.get('quantity_affected')} {form.get('quantity_unit') or ''}\n\n"
                    f"NARRATIVE\n{(form.get('description') or state.get('raw_text') or '')[:3500]}\n\n"
                    "Produce the investigation starting point."
                ),
                model=settings.reasoning_model,
            )
            llm_rc = _clean_root_causes(payload.get("root_causes"))
            llm_capa = _clean_capa(payload.get("capa"))
            llm_summary = str(payload.get("summary") or "").strip()

            if llm_rc:
                root_causes = llm_rc
            if llm_capa:
                capa = llm_capa
            if len(llm_summary) > 40:
                summary = llm_summary
            engine, model = "groq", settings.reasoning_model
        except LLMUnavailable as exc:
            note = f"Groq analysis unavailable, precedent library used ({exc})"

    return {
        "root_causes": root_causes,
        "capa": capa,
        "summary": summary,
        "_meta": {
            "engine": engine,
            "model": model,
            "note": note,
            "digest": {
                "hypotheses": len(root_causes),
                "capa_actions": len(capa),
                "top_cause": root_causes[0]["category"] if root_causes else None,
            },
        },
    }
