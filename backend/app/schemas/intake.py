from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    """A single form field the agent populated.

    ``confidence`` and ``evidence`` are first-class so the UI can show *why* a
    value was filled in — a reviewer must be able to challenge the machine.
    """

    value: Any = None
    confidence: float = 0.0
    evidence: str | None = None
    # "llm+regex": both engines agreed on an identifier field (extract.py's
    # _merge boosts confidence in that case). "analyst": a human-entered
    # value that overwrote both engines (extract.py, the reassess path) --
    # both are real, reachable values on this endpoint's own response path,
    # not exotic states. This Literal previously omitted both, which meant
    # the API only worked as long as the LLM was never actually live and no
    # analyst edit had round-tripped through /intake/reassess -- the 43-test
    # suite runs with GROQ_API_KEY unset, so neither path was ever exercised
    # until a live Groq key was used here for the first time.
    source: Literal["llm", "heuristic", "regex", "llm+regex", "analyst", "default", "none"] = "none"


class CompletenessGap(BaseModel):
    field: str
    label: str
    severity: Literal["blocker", "required", "recommended"] = "required"
    reason: str
    suggested_question: str | None = None


class DuplicateCandidate(BaseModel):
    complaint_id: str
    reference: str
    score: float
    matched_on: list[str]
    product_name: str | None = None
    batch_number: str | None = None
    complaint_type: str | None = None
    severity: str | None = None
    created_at: str | None = None
    rationale: str | None = None


class RiskAssessment(BaseModel):
    score: float = 0.0                    # 0-100
    band: str = "Unassessed"              # Low | Moderate | High | Severe
    severity: str | None = None
    priority: str | None = None
    patient_safety_impact: str | None = None
    batch_impact: str | None = None
    regulatory_flags: list[str] = Field(default_factory=list)
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str | None = None
    recommended_tat_days: int | None = None


class RootCauseHypothesis(BaseModel):
    category: str
    hypothesis: str
    likelihood: float = 0.0
    investigation_step: str | None = None


class CapaAction(BaseModel):
    type: Literal["correction", "corrective", "preventive"] = "corrective"
    action: str
    owner_function: str | None = None
    due_in_days: int | None = None
    effectiveness_check: str | None = None


class IntakeResult(BaseModel):
    run_id: str
    engine: str
    models: dict[str, str | None]
    duration_ms: int
    fields: dict[str, ExtractedField]
    form: dict[str, Any]
    summary: str | None = None
    completeness_score: float = 0.0
    gaps: list[CompletenessGap] = Field(default_factory=list)
    duplicates: list[DuplicateCandidate] = Field(default_factory=list)
    risk: RiskAssessment = Field(default_factory=RiskAssessment)
    root_causes: list[RootCauseHypothesis] = Field(default_factory=list)
    capa: list[CapaAction] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_text: str | None = None


class TextIntakeRequest(BaseModel):
    text: str = Field(min_length=10)
    channel: Literal["text", "email"] = "text"
    source_name: str | None = None


class ReassessRequest(BaseModel):
    form: dict[str, Any]
    source_text: str | None = None
