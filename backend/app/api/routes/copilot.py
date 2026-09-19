"""Conversational assistant bound to the draft complaint record."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import LLMUnavailable, llm
from app.agent.prompts import COPILOT_SYSTEM
from app.core.config import settings
from app.db.session import get_db
from app.models.complaint import CopilotMessage
from app.schemas.copilot import CopilotAction, CopilotRequest, CopilotResponse
from app.services import taxonomy as tax

router = APIRouter(prefix="/copilot", tags=["copilot"])

ALLOWED_ACTION_FIELDS = {
    "complaint_source", "customer_name", "customer_contact", "customer_country",
    "product_name", "product_strength", "dosage_form", "batch_number",
    "manufacturing_date", "expiry_date", "quantity_affected", "market_country",
    "complaint_type", "complaint_date", "date_received", "description",
    "sample_available", "severity", "priority",
}

STARTER_SUGGESTIONS = [
    "Why was this classified Critical?",
    "What do I still need before I can close triage?",
    "Draft the acknowledgement e-mail to the complainant.",
    "Which batches should we assess for impact?",
]


def _record_brief(form: dict) -> str:
    keys = [
        "complaint_source", "customer_name", "product_name", "product_strength",
        "dosage_form", "batch_number", "manufacturing_date", "expiry_date",
        "quantity_affected", "complaint_type", "complaint_date", "severity",
        "priority", "description",
    ]
    lines = [f"{k}: {form.get(k) if form.get(k) not in (None, '') else '— not provided —'}" for k in keys]
    return "\n".join(lines)


def _offline_reply(message: str, form: dict) -> CopilotResponse:
    """Useful, honest answers without a model — never a dead end."""
    lowered = message.lower()
    LABELS = {
        "product_name": "product name", "batch_number": "batch / lot number",
        "complaint_type": "complaint type", "description": "complaint description",
        "customer_name": "customer name", "expiry_date": "expiry date",
        "product_strength": "product strength",
    }
    missing = [LABELS[k] for k in LABELS if not form.get(k)]

    if any(w in lowered for w in ("severity", "critical", "classify", "classification")):
        severity = form.get("severity") or "not yet assessed"
        definition = tax.SEVERITY_DEFINITIONS.get(str(severity), "")
        reply = (
            f"Current classification is {severity}. {definition} "
            "Classification follows EU GMP Chapter 8 and the site's complaint SOP; "
            "the deciding factors are patient-safety impact, route of administration "
            "and market exposure."
        )
    elif any(w in lowered for w in ("missing", "complete", "need", "gap")):
        if missing:
            reply = (
                f"Still outstanding: {', '.join(missing)}. "
                "Product name and batch number are the blockers — without them the batch "
                "manufacturing record cannot be retrieved and no investigation can start."
            )
        else:
            reply = (
                "Nothing mandatory is outstanding. The record meets the minimum content "
                "required by 21 CFR 211.198(a): product, batch, nature of the complaint and "
                "an identifiable complainant."
            )
    elif any(w in lowered for w in ("capa", "action", "next step")):
        reply = (
            "Recommended sequence: quarantine the implicated batch, request the complaint "
            "sample, pull the batch manufacturing record, then open the investigation with a "
            "parallel recall assessment if the defect is Critical."
        )
    else:
        reply = (
            "The assistant is running without a language model (no GROQ_API_KEY configured), "
            "so I can only answer from the record itself. "
            f"Here is what is on file:\n\n{_record_brief(form)}"
        )
    return CopilotResponse(reply=reply, engine="heuristic", suggestions=STARTER_SUGGESTIONS[:3])


@router.get("/suggestions")
def suggestions() -> dict[str, list[str]]:
    return {"suggestions": STARTER_SUGGESTIONS}


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(CopilotMessage)
        .where(CopilotMessage.thread_id == thread_id)
        .order_by(CopilotMessage.created_at)
    ).scalars().all()
    return {
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    }


@router.post("", response_model=CopilotResponse)
def ask(payload: CopilotRequest, db: Session = Depends(get_db)) -> CopilotResponse:
    db.add(
        CopilotMessage(
            thread_id=payload.thread_id, complaint_id=payload.complaint_id,
            role="user", content=payload.message,
        )
    )

    history = db.execute(
        select(CopilotMessage)
        .where(CopilotMessage.thread_id == payload.thread_id)
        .order_by(CopilotMessage.created_at.desc())
        .limit(6)
    ).scalars().all()
    transcript = "\n".join(f"{m.role}: {m.content}" for m in reversed(history[1:]))

    if not llm.enabled:
        response = _offline_reply(payload.message, payload.form)
    else:
        try:
            raw = llm.complete_json(
                system=COPILOT_SYSTEM,
                user=(
                    f"CURRENT COMPLAINT RECORD\n{_record_brief(payload.form)}\n\n"
                    + (f"SOURCE DOCUMENT (excerpt)\n{payload.source_text[:2500]}\n\n"
                       if payload.source_text else "")
                    + (f"RECENT CONVERSATION\n{transcript}\n\n" if transcript else "")
                    + f"ANALYST QUESTION\n{payload.message}"
                ),
                model=settings.reasoning_model,
            )
            actions = [
                CopilotAction(
                    field=a["field"], value=a.get("value"), reason=a.get("reason"),
                )
                for a in (raw.get("actions") or [])
                if isinstance(a, dict) and a.get("field") in ALLOWED_ACTION_FIELDS
            ][:4]
            response = CopilotResponse(
                reply=str(raw.get("reply") or "").strip() or "I could not form an answer for that.",
                engine="groq",
                model=settings.reasoning_model,
                actions=actions,
                suggestions=[str(s) for s in (raw.get("suggestions") or [])][:3],
            )
        except LLMUnavailable:
            response = _offline_reply(payload.message, payload.form)
            response.reply = (
                "The language model is currently unreachable, so this answer comes from the "
                "rule-based assistant.\n\n" + response.reply
            )

    db.add(
        CopilotMessage(
            thread_id=payload.thread_id, complaint_id=payload.complaint_id,
            role="assistant", content=response.reply,
            citations={"actions": [a.model_dump() for a in response.actions]} if response.actions else None,
        )
    )
    return response
