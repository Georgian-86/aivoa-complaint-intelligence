"""Assemble the flat form payload the React store binds to."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.agent.nodes._base import traced
from app.services import heuristics
from app.services.taxonomy import COMPLAINT_STATUSES


@traced("finalise")
def finalise(state: dict, config: dict | None = None) -> dict[str, Any]:
    fields = state.get("fields") or {}
    risk = state.get("risk") or {}

    form: dict[str, Any] = {k: (v or {}).get("value") for k, v in fields.items()}

    severity = risk.get("severity")
    if severity:
        form["severity"] = severity
        form["priority"] = risk.get("priority") or heuristics.default_priority(severity)
        received = heuristics.parse_date(str(form.get("date_received") or "")) or date.today()
        form["due_date"] = (received + timedelta(days=heuristics.tat_days(severity))).isoformat()

    form["status"] = COMPLAINT_STATUSES[1]  # Pending Triage
    form.setdefault("quantity_unit", "units")

    # Count only the fields the agent was asked to extract — severity,
    # priority, status and due_date are derived, not extracted.
    populated = [k for k in fields if form.get(k) not in (None, "", [])]
    confidences = [
        (fields.get(k) or {}).get("confidence", 0.0)
        for k in fields
        if (fields.get(k) or {}).get("value") not in (None, "")
    ]
    overall = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    return {
        "form": form,
        "_meta": {
            "engine": "deterministic",
            "digest": {
                "fields_populated": len(populated),
                "fields_total": len(fields),
                "overall_confidence": overall,
                "severity": form.get("severity"),
                "due_date": form.get("due_date"),
            },
        },
    }
