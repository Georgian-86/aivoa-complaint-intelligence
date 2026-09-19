from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ComplaintBase(BaseModel):
    # Section 1 — Origin & customer details
    complaint_source: str | None = None
    customer_name: str | None = None
    customer_contact: str | None = None
    customer_country: str | None = None

    # Section 2 — Product & batch identification
    product_name: str | None = None
    product_strength: str | None = None
    dosage_form: str | None = None
    batch_number: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity_affected: float | None = None
    quantity_unit: str | None = "units"
    market_country: str | None = None

    # Section 3 — Complaint details
    complaint_type: str | None = None
    complaint_date: date | None = None
    date_received: date | None = None
    description: str | None = None
    sample_available: bool | None = None

    # Section 4 — Initial assessment & priority
    severity: str | None = None
    priority: str | None = None
    status: str | None = "Pending Triage"
    due_date: date | None = None


class ComplaintCreate(ComplaintBase):
    intake_channel: Literal["manual", "document", "text", "email"] = "manual"
    source_document_name: str | None = None
    source_text: str | None = None
    ai_summary: str | None = None
    ai_risk_score: float | None = None
    ai_risk_band: str | None = None
    ai_confidence: float | None = None
    ai_payload: dict[str, Any] | None = None
    agent_run_id: str | None = None


class ComplaintUpdate(ComplaintBase):
    ai_summary: str | None = None
    ai_payload: dict[str, Any] | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor: str
    actor_type: str
    action: str
    detail: str | None
    changes: dict[str, Any] | None
    created_at: datetime


class AgentNodeTraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    node: str
    label: str
    status: str
    engine: str | None
    model: str | None
    duration_ms: int
    output: dict[str, Any] | None
    note: str | None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    source_name: str | None
    status: str
    engine: str
    model_extraction: str | None
    model_reasoning: str | None
    duration_ms: int | None
    created_at: datetime
    traces: list[AgentNodeTraceOut] = []


class ComplaintOut(ComplaintBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    intake_channel: str
    source_document_name: str | None
    ai_summary: str | None
    ai_risk_score: float | None
    ai_risk_band: str | None
    ai_confidence: float | None
    ai_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    created_by: str


class ComplaintDetailOut(ComplaintOut):
    source_text: str | None = None
    audit_events: list[AuditEventOut] = []
    agent_runs: list[AgentRunOut] = []


class ComplaintListOut(BaseModel):
    items: list[ComplaintOut]
    total: int
    page: int
    page_size: int


class StatusPatch(BaseModel):
    status: str
    note: str | None = None
    actor: str = "qa.analyst"


class TaxonomyOut(BaseModel):
    complaint_sources: list[str]
    complaint_types: list[str]
    severities: list[str]
    severity_definitions: dict[str, str]
    severity_tat_days: dict[str, int]
    priorities: list[str]
    dosage_forms: list[str]
    statuses: list[str]
    root_cause_categories: list[str]


class AnalyticsOut(BaseModel):
    total: int
    open_count: int
    overdue_count: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    by_type: list[dict[str, Any]]
    by_month: list[dict[str, Any]]
    avg_risk_score: float | None
    ai_assisted_share: float
    top_products: list[dict[str, Any]] = Field(default_factory=list)
    recurrence: list[dict[str, Any]] = Field(default_factory=list)
