"""Duplicate complaint detection.

A weighted, explainable scorer rather than an embedding black box. In a
regulated workflow the analyst has to justify *why* two records were linked, so
each contribution is returned alongside the score.

Weights reflect how a QA reviewer actually reasons: same batch + same defect is
near-conclusive; same product family + same defect within a window is a trend
signal worth surfacing even when the batch differs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.complaint import Complaint

WEIGHTS = {
    "batch_number": 0.34,
    "product_name": 0.22,
    "complaint_type": 0.20,
    "description": 0.14,
    "customer_name": 0.06,
    "proximity": 0.04,
}


def _ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(str(a).lower(), str(b).lower()) / 100.0


def _exactish(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    a_n = str(a).strip().upper().replace("-", "").replace("/", "")
    b_n = str(b).strip().upper().replace("-", "").replace("/", "")
    if a_n == b_n:
        return 1.0
    return fuzz.ratio(a_n, b_n) / 100.0 if len(a_n) > 3 and len(b_n) > 3 else 0.0


def find_duplicates(
    db: Session,
    form: dict,
    *,
    exclude_id: str | None = None,
    limit: int = 4,
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.duplicate_lookback_days)
    stmt = select(Complaint).where(Complaint.created_at >= cutoff)
    if exclude_id:
        stmt = stmt.where(Complaint.id != exclude_id)
    candidates = db.execute(stmt.order_by(Complaint.created_at.desc()).limit(400)).scalars().all()

    results: list[dict] = []
    for candidate in candidates:
        parts: dict[str, float] = {
            "batch_number": _exactish(form.get("batch_number"), candidate.batch_number),
            "product_name": _ratio(form.get("product_name"), candidate.product_name),
            "complaint_type": 1.0
            if form.get("complaint_type") and form.get("complaint_type") == candidate.complaint_type
            else 0.0,
            "description": _ratio(form.get("description"), candidate.description),
            "customer_name": _ratio(form.get("customer_name"), candidate.customer_name),
        }

        # Recency proximity: complaints close in time about the same thing are
        # more likely to be the same event reported twice.
        created = candidate.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - created).days)
        parts["proximity"] = max(0.0, 1.0 - age_days / 90.0)

        score = sum(WEIGHTS[k] * v for k, v in parts.items())

        # A batch + defect match is materially stronger than the linear sum.
        if parts["batch_number"] > 0.95 and parts["complaint_type"] == 1.0:
            score = min(1.0, score + 0.18)

        if score < settings.duplicate_score_threshold:
            continue

        matched_on = [k for k, v in parts.items() if v >= 0.7 and k != "proximity"]
        rationale_bits = []
        if parts["batch_number"] > 0.95:
            rationale_bits.append("identical batch number")
        if parts["complaint_type"] == 1.0:
            rationale_bits.append("same defect category")
        if parts["product_name"] > 0.85:
            rationale_bits.append("same product")
        if parts["description"] > 0.7:
            rationale_bits.append("highly similar narrative")

        results.append(
            {
                "complaint_id": candidate.id,
                "reference": candidate.reference,
                "score": round(score, 3),
                "matched_on": matched_on,
                "product_name": candidate.product_name,
                "batch_number": candidate.batch_number,
                "complaint_type": candidate.complaint_type,
                "severity": candidate.severity,
                "created_at": candidate.created_at.isoformat(),
                "rationale": (
                    "Matches on " + ", ".join(rationale_bits) + "."
                    if rationale_bits
                    else "Aggregate similarity above threshold."
                ),
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
