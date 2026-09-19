"""LangGraph pipeline for complaint intake.

                      ┌──────────────┐
                      │   ingest     │  normalise + usability gate
                      └──────┬───────┘
                   unusable  │  usable
              ┌──────────────┴───────────────┐
              ▼                              ▼
         ┌─────────┐                   ┌──────────┐
         │finalise │                   │ extract  │  gpt-oss-20b + regex guardrail
         └─────────┘                   └────┬─────┘
                                            │ fan-out (same superstep)
                             ┌──────────────┴──────────────┐
                             ▼                             ▼
                     ┌──────────────┐              ┌──────────────┐
                     │ completeness │              │    dedupe    │
                     └──────┬───────┘              └──────┬───────┘
                            └──────────────┬──────────────┘
                                           ▼  join
                                    ┌──────────────┐
                                    │   classify   │  gpt-oss-120b + rule floor
                                    └──────┬───────┘
                                           ▼
                                    ┌──────────────┐
                                    │   analyse    │  RCA + CAPA + summary
                                    └──────┬───────┘
                                           ▼
                                    ┌──────────────┐
                                    │   finalise   │
                                    └──────────────┘

``completeness`` and ``dedupe`` are independent of each other and both depend
only on ``extract``, so they are declared as a fan-out: LangGraph runs them in
the same superstep and joins before ``classify``. The ``trace`` and ``warnings``
channels use ``operator.add`` reducers so the two branches merge cleanly.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes._base import NODE_LABELS
from app.agent.nodes.analyse import analyse
from app.agent.nodes.classify import classify
from app.agent.nodes.completeness import completeness
from app.agent.nodes.dedupe import dedupe
from app.agent.nodes.extract import extract
from app.agent.nodes.finalise import finalise
from app.agent.nodes.ingest import ingest
from app.agent.state import IntakeState
from app.core.config import settings

# Order used by the UI to render the progress rail before the run starts.
PIPELINE_STEPS: list[dict[str, str]] = [
    {"node": key, "label": NODE_LABELS[key]}
    for key in ("ingest", "extract", "completeness", "dedupe", "classify", "analyse", "finalise")
]


def _route_after_ingest(state: IntakeState) -> str:
    """Conditional edge — skip the expensive path for unusable input."""
    document = state.get("document") or {}
    return "extract" if document.get("usable") else "finalise"


def build_graph():
    builder = StateGraph(IntakeState)

    builder.add_node("ingest", ingest)
    builder.add_node("extract", extract)
    builder.add_node("completeness", completeness)
    builder.add_node("dedupe", dedupe)
    builder.add_node("classify", classify)
    builder.add_node("analyse", analyse)
    builder.add_node("finalise", finalise)

    builder.add_edge(START, "ingest")
    builder.add_conditional_edges(
        "ingest", _route_after_ingest, {"extract": "extract", "finalise": "finalise"}
    )

    # Fan-out / fan-in.
    builder.add_edge("extract", "completeness")
    builder.add_edge("extract", "dedupe")
    builder.add_edge("completeness", "classify")
    builder.add_edge("dedupe", "classify")

    builder.add_edge("classify", "analyse")
    builder.add_edge("analyse", "finalise")
    builder.add_edge("finalise", END)

    return builder.compile()


# Compiled once at import; the graph is stateless between runs.
GRAPH = build_graph()


def _initial_state(
    *, raw_text: str, channel: str, source_name: str | None, existing_form: dict | None
) -> IntakeState:
    return {
        "run_id": str(uuid.uuid4()),
        "raw_text": raw_text,
        "channel": channel,
        "source_name": source_name,
        "existing_form": existing_form or {},
        "trace": [],
        "warnings": [],
        "engine": "heuristic",
    }


def run_intake(
    *,
    raw_text: str,
    channel: str = "document",
    source_name: str | None = None,
    existing_form: dict | None = None,
    db=None,
) -> dict[str, Any]:
    """Execute the pipeline to completion and return the final state."""
    started = time.perf_counter()
    state = _initial_state(
        raw_text=raw_text, channel=channel, source_name=source_name, existing_form=existing_form
    )
    final = GRAPH.invoke(state, config={"configurable": {"db": db}})
    final["duration_ms"] = int((time.perf_counter() - started) * 1000)
    final["models"] = {
        "extraction": settings.extraction_model if settings.llm_enabled else None,
        "reasoning": settings.reasoning_model if settings.llm_enabled else None,
    }
    return final


def stream_intake(
    *,
    raw_text: str,
    channel: str = "document",
    source_name: str | None = None,
    existing_form: dict | None = None,
    db=None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(event, payload)`` pairs as each node completes.

    Drives the live extraction rail in the UI. The final event carries the
    complete state so the client never needs a second round trip.
    """
    started = time.perf_counter()
    state = _initial_state(
        raw_text=raw_text, channel=channel, source_name=source_name, existing_form=existing_form
    )

    yield "start", {
        "run_id": state["run_id"],
        "steps": PIPELINE_STEPS,
        "engine": "groq" if settings.llm_enabled else "heuristic",
    }

    accumulated: dict[str, Any] = dict(state)
    completed = 0
    try:
        for chunk in GRAPH.stream(state, config={"configurable": {"db": db}}, stream_mode="updates"):
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                for key, value in update.items():
                    if key in {"trace", "warnings"}:
                        accumulated.setdefault(key, [])
                        accumulated[key] = [*accumulated[key], *(value or [])]
                    else:
                        accumulated[key] = value
                completed += 1
                trace_tail = (update.get("trace") or [{}])[-1]
                yield "node", {
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "status": trace_tail.get("status", "ok"),
                    "engine": trace_tail.get("engine"),
                    "model": trace_tail.get("model"),
                    "duration_ms": trace_tail.get("duration_ms", 0),
                    "output": trace_tail.get("output"),
                    "note": trace_tail.get("note"),
                    "progress": round(min(0.99, completed / len(PIPELINE_STEPS)), 2),
                }
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as an event
        yield "error", {"message": str(exc)[:400]}
        return

    accumulated["duration_ms"] = int((time.perf_counter() - started) * 1000)
    accumulated["models"] = {
        "extraction": settings.extraction_model if settings.llm_enabled else None,
        "reasoning": settings.reasoning_model if settings.llm_enabled else None,
    }
    yield "complete", accumulated
