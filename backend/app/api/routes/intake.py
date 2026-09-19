"""Intake endpoints — the AI Complaint Intake Assistant's server side."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.graph import PIPELINE_STEPS, run_intake, stream_intake
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.complaint import AgentNodeTrace, AgentRun
from app.schemas.intake import IntakeResult, ReassessRequest, TextIntakeRequest
from app.services.documents import SUPPORTED_EXTENSIONS, parse_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])


# ── persistence of the run ---------------------------------------------------
def _persist_run(db: Session, state: dict[str, Any], *, channel: str, source_name: str | None) -> str:
    run = AgentRun(
        id=state.get("run_id"),
        channel=channel,
        source_name=source_name,
        input_chars=len(state.get("raw_text") or ""),
        status="error" if any(t.get("status") == "error" for t in state.get("trace", [])) else "complete",
        engine=state.get("engine", "heuristic"),
        model_extraction=(state.get("models") or {}).get("extraction"),
        model_reasoning=(state.get("models") or {}).get("reasoning"),
        duration_ms=state.get("duration_ms"),
        result={
            "form": state.get("form"),
            "risk": state.get("risk"),
            "completeness_score": state.get("completeness_score"),
            "gaps": state.get("gaps"),
            "duplicates": state.get("duplicates"),
            "root_causes": state.get("root_causes"),
            "capa": state.get("capa"),
            "summary": state.get("summary"),
        },
    )
    db.add(run)
    for index, entry in enumerate(state.get("trace") or []):
        db.add(
            AgentNodeTrace(
                run_id=run.id,
                sequence=index,
                node=entry.get("node", "?"),
                label=entry.get("label", "?"),
                status=entry.get("status", "ok"),
                engine=entry.get("engine"),
                model=entry.get("model"),
                duration_ms=entry.get("duration_ms", 0),
                output=entry.get("output"),
                note=entry.get("note"),
            )
        )
    db.flush()
    return run.id


def _to_result(state: dict[str, Any]) -> IntakeResult:
    return IntakeResult(
        run_id=state.get("run_id", ""),
        engine=state.get("engine", "heuristic"),
        models=state.get("models") or {},
        duration_ms=state.get("duration_ms", 0),
        fields=state.get("fields") or {},
        form=state.get("form") or {},
        summary=state.get("summary"),
        completeness_score=state.get("completeness_score", 0.0),
        gaps=state.get("gaps") or [],
        duplicates=state.get("duplicates") or [],
        risk=state.get("risk") or {},
        root_causes=state.get("root_causes") or [],
        capa=state.get("capa") or [],
        clarifying_questions=state.get("clarifying_questions") or [],
        trace=state.get("trace") or [],
        warnings=state.get("warnings") or [],
        source_text=state.get("raw_text"),
    )


# ── metadata -----------------------------------------------------------------
@router.get("/pipeline")
def pipeline() -> dict[str, Any]:
    """Describe the agent graph so the UI can render the rail before running."""
    return {
        "steps": PIPELINE_STEPS,
        "engine": "groq" if settings.llm_enabled else "heuristic",
        "models": {
            "extraction": settings.extraction_model,
            "reasoning": settings.reasoning_model,
        },
        "llm_configured": settings.llm_enabled,
        "supported_formats": sorted(SUPPORTED_EXTENSIONS),
        "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
    }


# ── synchronous runs ---------------------------------------------------------
@router.post("/text", response_model=IntakeResult)
def intake_text(payload: TextIntakeRequest, db: Session = Depends(get_db)) -> IntakeResult:
    state = run_intake(
        raw_text=payload.text,
        channel=payload.channel,
        source_name=payload.source_name or "Pasted text",
        db=db,
    )
    _persist_run(db, state, channel=payload.channel, source_name=payload.source_name)
    return _to_result(state)


@router.post("/document", response_model=IntakeResult)
async def intake_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IntakeResult:
    data = await file.read()
    try:
        document = parse_document(file.filename or "upload", data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = run_intake(
        raw_text=document.text,
        channel="document",
        source_name=document.filename,
        db=db,
    )
    state["warnings"] = [*(state.get("warnings") or []), *document.warnings]
    _persist_run(db, state, channel="document", source_name=document.filename)

    result = _to_result(state)
    return result


@router.post("/reassess", response_model=IntakeResult)
def reassess(payload: ReassessRequest, db: Session = Depends(get_db)) -> IntakeResult:
    """Re-run risk, duplicates and CAPA against analyst-edited form values."""
    text = payload.source_text or payload.form.get("description") or ""
    if not text.strip():
        raise HTTPException(status_code=422, detail="Nothing to assess — add a description first.")
    state = run_intake(
        raw_text=text,
        channel="manual",
        source_name="Analyst re-assessment",
        existing_form={k: v for k, v in payload.form.items() if v not in (None, "", [])},
        db=db,
    )
    _persist_run(db, state, channel="manual", source_name="Analyst re-assessment")
    return _to_result(state)


# ── streaming run ------------------------------------------------------------
def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _event_stream(*, raw_text: str, channel: str, source_name: str | None, extra_warnings: list[str]):
    """Own the DB session for the whole stream — request scope ends too early."""
    db = SessionLocal()
    final_state: dict[str, Any] | None = None
    try:
        for event, payload in stream_intake(
            raw_text=raw_text, channel=channel, source_name=source_name, db=db
        ):
            if event == "complete":
                final_state = payload
                payload["warnings"] = [*(payload.get("warnings") or []), *extra_warnings]
                _persist_run(db, payload, channel=channel, source_name=source_name)
                db.commit()
                yield _sse("complete", _to_result(payload).model_dump(mode="json"))
            else:
                yield _sse(event, payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("intake stream failed")
        db.rollback()
        yield _sse("error", {"message": str(exc)[:400]})
    finally:
        db.close()
    if final_state is None:
        yield _sse("error", {"message": "Pipeline terminated without a result."})


@router.post("/stream")
async def intake_stream(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    channel: str = Form(default="document"),
):
    """Server-Sent Events version of the pipeline.

    The UI binds each ``node`` event to the extraction progress rail, so the
    analyst watches the agent work instead of staring at a spinner.
    """
    warnings: list[str] = []
    if file is not None and file.filename:
        data = await file.read()
        try:
            document = parse_document(file.filename, data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raw_text, source_name, warnings = document.text, document.filename, document.warnings
        channel = "document"
    elif text and text.strip():
        raw_text, source_name = text, "Pasted text"
        channel = channel if channel in {"text", "email"} else "text"
    else:
        raise HTTPException(status_code=422, detail="Provide either a file or complaint text.")

    return StreamingResponse(
        _event_stream(
            raw_text=raw_text, channel=channel, source_name=source_name, extra_warnings=warnings
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
