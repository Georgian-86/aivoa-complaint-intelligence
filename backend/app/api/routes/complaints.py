"""Complaint register CRUD + workflow transitions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.complaint import AuditEvent, Complaint
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintDetailOut,
    ComplaintListOut,
    ComplaintOut,
    ComplaintUpdate,
    StatusPatch,
    TaxonomyOut,
)
from app.services import taxonomy as tax
from app.services.similarity import find_duplicates

router = APIRouter(prefix="/complaints", tags=["complaints"])

TRACKED_FIELDS = (
    "complaint_source", "customer_name", "product_name", "product_strength",
    "batch_number", "complaint_type", "severity", "priority", "status",
    "description", "expiry_date", "quantity_affected",
)


def next_reference(db: Session) -> str:
    """Human-readable, sortable complaint reference: CMP-YYYY-NNNN."""
    year = date.today().year
    prefix = f"CMP-{year}-"
    latest = db.execute(
        select(Complaint.reference)
        .where(Complaint.reference.like(f"{prefix}%"))
        .order_by(Complaint.reference.desc())
        .limit(1)
    ).scalar_one_or_none()
    nxt = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    return f"{prefix}{nxt:04d}"


def log_audit(
    db: Session, complaint: Complaint, *, action: str, detail: str | None = None,
    actor: str = "qa.analyst", actor_type: str = "human", changes: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            complaint_id=complaint.id, actor=actor, actor_type=actor_type,
            action=action, detail=detail, changes=changes,
        )
    )


@router.get("/taxonomy", response_model=TaxonomyOut)
def get_taxonomy() -> TaxonomyOut:
    return TaxonomyOut(
        complaint_sources=tax.COMPLAINT_SOURCES,
        complaint_types=tax.COMPLAINT_TYPES,
        severities=tax.SEVERITIES,
        severity_definitions=tax.SEVERITY_DEFINITIONS,
        severity_tat_days=tax.SEVERITY_TAT_DAYS,
        priorities=tax.PRIORITIES,
        dosage_forms=tax.DOSAGE_FORMS,
        statuses=tax.COMPLAINT_STATUSES,
        root_cause_categories=tax.ROOT_CAUSE_CATEGORIES,
    )


@router.get("", response_model=ComplaintListOut)
def list_complaints(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Free text across reference, product, batch, customer"),
    severity: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    complaint_type: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="-created_at"),
) -> ComplaintListOut:
    stmt = select(Complaint)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Complaint.reference.ilike(like),
                Complaint.product_name.ilike(like),
                Complaint.batch_number.ilike(like),
                Complaint.customer_name.ilike(like),
                Complaint.description.ilike(like),
            )
        )
    if severity:
        stmt = stmt.where(Complaint.severity.in_(severity))
    if status:
        stmt = stmt.where(Complaint.status.in_(status))
    if complaint_type:
        stmt = stmt.where(Complaint.complaint_type.in_(complaint_type))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    column_name = sort.lstrip("-")
    column = getattr(Complaint, column_name, Complaint.created_at)
    stmt = stmt.order_by(column.desc() if sort.startswith("-") else column.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    items = db.execute(stmt).scalars().all()
    return ComplaintListOut(items=list(items), total=total, page=page, page_size=page_size)


@router.post("", response_model=ComplaintDetailOut, status_code=201)
def create_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)) -> Complaint:
    data = payload.model_dump(exclude_unset=True, exclude={"agent_run_id"})
    complaint = Complaint(reference=next_reference(db), **data)
    if not complaint.status:
        complaint.status = "Pending Triage"
    if not complaint.date_received:
        complaint.date_received = date.today()
    db.add(complaint)
    db.flush()

    log_audit(
        db, complaint, action="created",
        detail=f"Complaint logged via {complaint.intake_channel} intake.",
        changes={"reference": complaint.reference},
    )
    if payload.ai_payload or payload.ai_summary:
        log_audit(
            db, complaint, action="ai_assessment_attached", actor="intake-agent", actor_type="agent",
            detail=(
                f"LangGraph intake run produced severity={complaint.severity}, "
                f"risk={complaint.ai_risk_score} ({complaint.ai_risk_band})."
            ),
            changes={"agent_run_id": payload.agent_run_id},
        )

    # Bind the agent run to the saved complaint for traceability.
    if payload.agent_run_id:
        from app.models.complaint import AgentRun

        run = db.get(AgentRun, payload.agent_run_id)
        if run:
            run.complaint_id = complaint.id

    db.flush()
    db.refresh(complaint)
    return complaint


@router.get("/{complaint_id}", response_model=ComplaintDetailOut)
def get_complaint(complaint_id: str, db: Session = Depends(get_db)) -> Complaint:
    complaint = db.execute(
        select(Complaint)
        .where(Complaint.id == complaint_id)
        .options(
            selectinload(Complaint.audit_events),
            selectinload(Complaint.agent_runs),
        )
    ).scalar_one_or_none()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.patch("/{complaint_id}", response_model=ComplaintDetailOut)
def update_complaint(
    complaint_id: str, payload: ComplaintUpdate, db: Session = Depends(get_db)
) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    changes: dict[str, Any] = {}
    for key, value in payload.model_dump(exclude_unset=True).items():
        before = getattr(complaint, key, None)
        if before != value:
            changes[key] = {"from": str(before) if before is not None else None,
                            "to": str(value) if value is not None else None}
            setattr(complaint, key, value)

    if changes:
        log_audit(
            db, complaint, action="updated",
            detail=f"{len(changes)} field(s) amended: " + ", ".join(sorted(changes)),
            changes={k: v for k, v in changes.items() if k in TRACKED_FIELDS} or changes,
        )
    db.flush()
    db.refresh(complaint)
    return complaint


@router.post("/{complaint_id}/status", response_model=ComplaintDetailOut)
def transition_status(
    complaint_id: str, payload: StatusPatch, db: Session = Depends(get_db)
) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if payload.status not in tax.COMPLAINT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status '{payload.status}'")

    previous = complaint.status
    complaint.status = payload.status
    log_audit(
        db, complaint, action="status_changed", actor=payload.actor,
        detail=payload.note or f"{previous} → {payload.status}",
        changes={"status": {"from": previous, "to": payload.status}},
    )
    db.flush()
    db.refresh(complaint)
    return complaint


@router.get("/{complaint_id}/duplicates")
def complaint_duplicates(complaint_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    form = {
        "batch_number": complaint.batch_number,
        "product_name": complaint.product_name,
        "complaint_type": complaint.complaint_type,
        "description": complaint.description,
        "customer_name": complaint.customer_name,
    }
    return {"matches": find_duplicates(db, form, exclude_id=complaint.id, limit=6)}


@router.delete("/{complaint_id}", status_code=204, response_class=Response)
def delete_complaint(complaint_id: str, db: Session = Depends(get_db)) -> Response:
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    db.delete(complaint)
    return Response(status_code=204)
