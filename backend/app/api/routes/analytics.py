"""Register-level analytics for the QA dashboard."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import AnalyticsOut
from app.services.taxonomy import SEVERITIES

SEVERITY_RANK = {"Minor": 0, "Major": 1, "Critical": 2}

OPEN_STATUSES = {"Draft", "Pending Triage", "Under Investigation", "CAPA Initiated",
                 "Pending Closure Approval"}

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOut)
def overview(db: Session = Depends(get_db)) -> AnalyticsOut:
    rows = db.execute(select(Complaint)).scalars().all()
    today = date.today()

    by_severity = Counter()
    by_status = Counter()
    by_type = Counter()
    by_month = Counter()
    by_product = Counter()
    risk_scores: list[float] = []
    ai_assisted = 0
    overdue = 0

    for row in rows:
        by_severity[row.severity or "Unclassified"] += 1
        by_status[row.status or "Unknown"] += 1
        if row.complaint_type:
            by_type[row.complaint_type] += 1
        if row.product_name:
            by_product[row.product_name] += 1
        by_month[row.created_at.strftime("%Y-%m")] += 1
        if row.ai_risk_score is not None:
            risk_scores.append(row.ai_risk_score)
        if row.intake_channel in {"document", "text", "email"}:
            ai_assisted += 1
        if row.due_date and row.due_date < today and row.status in OPEN_STATUSES:
            overdue += 1

    # ── Recurrence watchlist ─────────────────────────────────────────────────
    # A repeat defect on the same product family is the signal a QA reviewer
    # actually acts on: three "minor" events of the same kind are not three
    # minor events, they are a trend.
    clusters: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not row.product_name or not row.complaint_type:
            continue
        key = (row.product_name, row.complaint_type)
        bucket = clusters.setdefault(key, {
            "product_name": row.product_name,
            "complaint_type": row.complaint_type,
            "count": 0, "batches": set(), "worst_severity": "Minor",
            "latest": row.created_at,
        })
        bucket["count"] += 1
        if row.batch_number:
            bucket["batches"].add(row.batch_number)
        if SEVERITY_RANK.get(row.severity or "Minor", 0) > SEVERITY_RANK[bucket["worst_severity"]]:
            bucket["worst_severity"] = row.severity
        bucket["latest"] = max(bucket["latest"], row.created_at)

    recurrence = sorted(
        (
            {
                "product_name": b["product_name"],
                "complaint_type": b["complaint_type"],
                "count": b["count"],
                "batch_count": len(b["batches"]),
                "batches": sorted(b["batches"])[:4],
                "worst_severity": b["worst_severity"],
                "latest": b["latest"].isoformat(),
            }
            for b in clusters.values() if b["count"] >= 2
        ),
        key=lambda r: (r["count"], SEVERITY_RANK.get(r["worst_severity"], 0)),
        reverse=True,
    )[:6]

    total = len(rows)
    return AnalyticsOut(
        total=total,
        open_count=sum(v for k, v in by_status.items() if k in OPEN_STATUSES),
        overdue_count=overdue,
        by_severity={s: by_severity.get(s, 0) for s in [*SEVERITIES, "Unclassified"]},
        by_status=dict(by_status),
        by_type=[{"name": k, "count": v} for k, v in by_type.most_common(8)],
        by_month=[{"month": m, "count": c} for m, c in sorted(by_month.items())][-12:],
        avg_risk_score=round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else None,
        ai_assisted_share=round(ai_assisted / total, 3) if total else 0.0,
        top_products=[{"name": k, "count": v} for k, v in by_product.most_common(5)],
        recurrence=recurrence,
    )
