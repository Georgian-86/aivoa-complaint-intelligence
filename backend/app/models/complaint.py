"""ORM models for the complaint record and its GxP satellites.

Design notes
------------
* ``Complaint`` mirrors the minimum record mandated by 21 CFR 211.198(a) plus
  the triage fields a modern QMS carries.
* ``AgentRun`` / ``AgentNodeTrace`` persist *how* the AI reached a conclusion.
  In a regulated system the recommendation is worthless without the audit
  trail behind it, so every node's input digest, output and latency is stored.
* ``AuditEvent`` is append-only and models the ALCOA+ expectation that records
  are attributable and traceable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    # ── 1. Origin & customer details ─────────────────────────────────────────
    complaint_source: Mapped[str | None] = mapped_column(String(120))
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_contact: Mapped[str | None] = mapped_column(String(240))
    customer_country: Mapped[str | None] = mapped_column(String(120))

    # ── 2. Product & batch identification ────────────────────────────────────
    product_name: Mapped[str | None] = mapped_column(String(240), index=True)
    product_strength: Mapped[str | None] = mapped_column(String(120))
    dosage_form: Mapped[str | None] = mapped_column(String(120))
    batch_number: Mapped[str | None] = mapped_column(String(120), index=True)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quantity_affected: Mapped[float | None] = mapped_column(Float)
    quantity_unit: Mapped[str | None] = mapped_column(String(32), default="units")
    market_country: Mapped[str | None] = mapped_column(String(120))

    # ── 3. Complaint details ─────────────────────────────────────────────────
    complaint_type: Mapped[str | None] = mapped_column(String(120), index=True)
    complaint_date: Mapped[date | None] = mapped_column(Date)
    date_received: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    sample_available: Mapped[bool | None] = mapped_column(Boolean)

    # ── 4. Initial assessment & priority ─────────────────────────────────────
    severity: Mapped[str | None] = mapped_column(String(32), index=True)
    priority: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(48), default="Pending Triage", index=True)
    due_date: Mapped[date | None] = mapped_column(Date)

    # ── AI outputs (persisted so the record is self-contained) ───────────────
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_risk_score: Mapped[float | None] = mapped_column(Float)
    ai_risk_band: Mapped[str | None] = mapped_column(String(32))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_payload: Mapped[dict | None] = mapped_column(JSON)  # rca, capa, flags, gaps

    # ── Provenance ───────────────────────────────────────────────────────────
    intake_channel: Mapped[str] = mapped_column(String(32), default="manual")
    source_document_name: Mapped[str | None] = mapped_column(String(320))
    source_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    created_by: Mapped[str] = mapped_column(String(120), default="qa.analyst")

    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="AgentRun.created_at"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="AuditEvent.created_at"
    )


Index("ix_complaints_triage", Complaint.status, Complaint.severity)


class AgentRun(Base):
    """One full traversal of the LangGraph intake pipeline."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    complaint_id: Mapped[str | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )

    channel: Mapped[str] = mapped_column(String(32), default="document")
    source_name: Mapped[str | None] = mapped_column(String(320))
    input_chars: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(24), default="running")
    engine: Mapped[str] = mapped_column(String(32), default="groq")  # groq | heuristic
    model_extraction: Mapped[str | None] = mapped_column(String(64))
    model_reasoning: Mapped[str | None] = mapped_column(String(64))

    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    complaint: Mapped["Complaint | None"] = relationship(back_populates="agent_runs")
    traces: Mapped[list["AgentNodeTrace"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentNodeTrace.sequence"
    )


class AgentNodeTrace(Base):
    """Per-node execution record — the explainability spine of the system."""

    __tablename__ = "agent_node_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    node: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="ok")
    engine: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["AgentRun"] = relationship(back_populates="traces")


class AuditEvent(Base):
    """Append-only audit trail (ALCOA+ / 21 CFR Part 11 flavoured)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    complaint_id: Mapped[str] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )
    actor: Mapped[str] = mapped_column(String(120), default="qa.analyst")
    actor_type: Mapped[str] = mapped_column(String(16), default="human")  # human | agent
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    complaint: Mapped["Complaint"] = relationship(back_populates="audit_events")


class CopilotMessage(Base):
    """Conversation held with the intake assistant about a draft complaint."""

    __tablename__ = "copilot_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    complaint_id: Mapped[str | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
