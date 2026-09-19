"""Risk classification node.

The LLM proposes; the rule engine holds a floor. If the deterministic layer
detects a patient-safety signal (hospitalisation, sterility failure, mix-up)
and the model came back with something softer, the rule wins and the override
is recorded in the trace. Under-classifying a critical defect is the one
failure mode this system must not have.
"""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMUnavailable, llm
from app.agent.nodes._base import traced
from app.agent.prompts import RISK_SYSTEM
from app.core.config import settings
from app.services import heuristics
from app.services.taxonomy import REGULATORY_FLAGS, SEVERITIES

SEVERITY_RANK = {"Minor": 0, "Major": 1, "Critical": 2}
BANDS = (("Severe", 75), ("High", 50), ("Moderate", 25), ("Low", 0))


def _band(score: float) -> str:
    for name, floor in BANDS:
        if score >= floor:
            return name
    return "Low"


@traced("classify")
def classify(state: dict, config: dict | None = None) -> dict[str, Any]:
    fields = state.get("fields") or {}
    form = {k: (v or {}).get("value") for k, v in fields.items()}
    text = state.get("raw_text") or form.get("description") or ""

    # ── deterministic baseline ───────────────────────────────────────────────
    rule_severity, _conf, rule_drivers = heuristics.detect_severity(text, form.get("complaint_type"))
    rule_score, rule_band = heuristics.score_risk(rule_severity, rule_drivers, text)

    risk: dict[str, Any] = {
        "severity": rule_severity,
        "priority": heuristics.default_priority(rule_severity),
        "score": rule_score,
        "band": rule_band,
        "patient_safety_impact": None,
        "batch_impact": None,
        "regulatory_flags": heuristics.regulatory_flags(rule_severity, form.get("complaint_type"), text),
        "drivers": rule_drivers,
        "rationale": None,
        "recommended_tat_days": heuristics.tat_days(rule_severity),
    }

    engine, model, note = "heuristic", None, None
    warnings: list[str] = []

    # ── model assessment ─────────────────────────────────────────────────────
    if llm.enabled:
        try:
            payload = llm.complete_json(
                system=RISK_SYSTEM,
                user=(
                    "COMPLAINT RECORD\n"
                    f"Product: {form.get('product_name')} {form.get('product_strength') or ''}\n"
                    f"Dosage form: {form.get('dosage_form')}\n"
                    f"Batch: {form.get('batch_number')}  Expiry: {form.get('expiry_date')}\n"
                    f"Defect category: {form.get('complaint_type')}\n"
                    f"Quantity affected: {form.get('quantity_affected')} {form.get('quantity_unit') or ''}\n"
                    f"Reported by: {form.get('customer_name')} via {form.get('complaint_source')}\n\n"
                    f"NARRATIVE\n{(form.get('description') or text)[:4000]}\n\n"
                    "Assess the risk now."
                ),
                model=settings.reasoning_model,
            )

            severity = str(payload.get("severity") or "").strip().title()
            if severity not in SEVERITIES:
                severity = rule_severity

            try:
                score = float(payload.get("score") or rule_score)
            except (TypeError, ValueError):
                score = rule_score
            score = max(0.0, min(100.0, score))

            drivers = [
                d for d in (payload.get("drivers") or [])
                if isinstance(d, dict) and d.get("factor")
            ][:4]

            flags = [
                f for f in (payload.get("regulatory_flags") or []) if f in REGULATORY_FLAGS
            ]

            risk.update(
                {
                    "severity": severity,
                    "score": round(score, 1),
                    "band": _band(score),
                    "patient_safety_impact": payload.get("patient_safety_impact"),
                    "batch_impact": payload.get("batch_impact"),
                    "regulatory_flags": flags,
                    "drivers": drivers or rule_drivers,
                    "rationale": payload.get("rationale"),
                }
            )
            priority = str(payload.get("priority") or "").strip()
            risk["priority"] = priority if priority else heuristics.default_priority(severity)
            engine, model = "groq", settings.reasoning_model
        except LLMUnavailable as exc:
            note = f"Groq risk assessment unavailable, rule engine used ({exc})"
            warnings.append(
                "Risk was classified by the rule engine because the language model was "
                "unreachable. A QA reviewer must confirm the classification."
            )

    # ── safety floor: never let the model de-escalate a rule-detected critical ─
    if SEVERITY_RANK[rule_severity] > SEVERITY_RANK.get(risk["severity"], 0):
        note = (
            f"Rule engine escalated {risk['severity']} → {rule_severity}: "
            "a patient-safety or sterile-route signal was present in the source text."
        )
        risk["severity"] = rule_severity
        risk["priority"] = heuristics.default_priority(rule_severity)
        risk["score"] = max(risk["score"], rule_score)
        risk["band"] = _band(risk["score"])
        risk["drivers"] = (risk.get("drivers") or []) + rule_drivers
        risk["override"] = "rule_engine_escalation"
        warnings.append(
            "Severity was escalated by the deterministic safety rule. Review the drivers before accepting."
        )

    # Regulatory flags are additive — a rule-detected flag is never dropped.
    rule_flags = heuristics.regulatory_flags(risk["severity"], form.get("complaint_type"), text)
    risk["regulatory_flags"] = sorted(set(risk["regulatory_flags"]) | set(rule_flags))
    risk["recommended_tat_days"] = heuristics.tat_days(risk["severity"])
    risk["flag_definitions"] = {f: REGULATORY_FLAGS[f] for f in risk["regulatory_flags"]}

    return {
        "risk": risk,
        "warnings": warnings,
        "_meta": {
            "engine": engine,
            "model": model,
            "note": note,
            "digest": {
                "severity": risk["severity"],
                "score": risk["score"],
                "band": risk["band"],
                "flags": risk["regulatory_flags"],
            },
        },
    }
