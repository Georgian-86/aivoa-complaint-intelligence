"""Shared state object threaded through the LangGraph pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class IntakeState(TypedDict, total=False):
    # ── inputs ───────────────────────────────────────────────────────────────
    run_id: str
    raw_text: str
    source_name: str | None
    channel: str
    existing_form: dict[str, Any]     # analyst-entered values (never overwritten)

    # ── node outputs ─────────────────────────────────────────────────────────
    document: dict[str, Any]          # normalised text + detected structure
    fields: dict[str, Any]            # field -> {value, confidence, evidence, source}
    form: dict[str, Any]              # flattened values ready for the UI form
    completeness_score: float
    gaps: list[dict[str, Any]]
    clarifying_questions: list[str]
    duplicates: list[dict[str, Any]]
    risk: dict[str, Any]
    root_causes: list[dict[str, Any]]
    capa: list[dict[str, Any]]
    summary: str | None

    # ── bookkeeping (reducers let parallel branches append safely) ───────────
    trace: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    engine: str
