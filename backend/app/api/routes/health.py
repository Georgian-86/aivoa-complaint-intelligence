from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agent.llm import LLMUnavailable, llm
from app.core.config import settings
from app.db.session import get_db
from app.models.complaint import Complaint

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        complaints = db.execute(select(Complaint.id)).scalars().all()
        database = {"status": "up", "dialect": db.bind.dialect.name, "complaints": len(complaints)}
    except Exception as exc:  # noqa: BLE001
        database = {"status": "down", "error": str(exc)[:200]}

    return {
        "status": "ok" if database["status"] == "up" else "degraded",
        "app": settings.app_name,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "ai": {
            "provider": "groq",
            "configured": settings.llm_enabled,
            "extraction_model": settings.extraction_model,
            "reasoning_model": settings.reasoning_model,
            "mode": "llm" if settings.llm_enabled else "deterministic-fallback",
        },
    }


@router.get("/health/llm")
def llm_probe() -> dict:
    """Verify the Groq credentials and both configured models, live.

    Makes one tiny structured call per model and reports latency and the exact
    error if either fails. This is the first thing to hit after pasting a key:
    a model that has been decommissioned upstream fails here in one second
    rather than silently degrading every intake run to the rule engine.
    """
    if not settings.llm_enabled:
        return {
            "configured": False,
            "mode": "deterministic-fallback",
            "hint": "Set GROQ_API_KEY in backend/.env and restart the API.",
            "models": {},
        }

    results: dict[str, dict] = {}
    for role, model in (
        ("extraction", settings.extraction_model),
        ("reasoning", settings.reasoning_model),
    ):
        started = time.perf_counter()
        try:
            payload = llm.complete_json(
                system=(
                    "You are a health probe. Reply with exactly this JSON object "
                    'and nothing else: {"ok": true}'
                ),
                user="Respond now.",
                model=model,
            )
            results[role] = {
                "model": model,
                "status": "ok" if payload.get("ok") is not None else "unexpected_payload",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "response": payload,
            }
        except LLMUnavailable as exc:
            results[role] = {
                "model": model,
                "status": "error",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": str(exc)[:400],
                "hint": (
                    "If this says the model was decommissioned, pick a current one from "
                    "https://console.groq.com/docs/models and set EXTRACTION_MODEL / "
                    "REASONING_MODEL in backend/.env."
                ),
            }

    healthy = all(r["status"] == "ok" for r in results.values())
    return {
        "configured": True,
        "status": "ok" if healthy else "degraded",
        "mode": "llm" if healthy else "partial",
        "models": results,
    }
