"""Node helpers: timing, tracing and uniform degradation reporting."""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

NODE_LABELS: dict[str, str] = {
    "ingest": "Reading source document",
    "extract": "Extracting complaint fields",
    "completeness": "Checking record completeness",
    "dedupe": "Searching for duplicate complaints",
    "classify": "Assessing GMP risk and severity",
    "analyse": "Proposing root cause and CAPA",
    "finalise": "Assembling complaint record",
}


def traced(name: str) -> Callable:
    """Wrap a node so it records duration, engine and a compact output digest."""

    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(fn)
        def wrapper(state: dict, config: dict | None = None) -> dict:
            started = time.perf_counter()
            status, note, engine, model = "ok", None, None, None
            try:
                result = fn(state, config) or {}
            except Exception as exc:  # noqa: BLE001 - a node must never kill the run
                logger.exception("node %s failed", name)
                status, note, result = "error", str(exc)[:300], {
                    "warnings": [f"{NODE_LABELS.get(name, name)} failed: {exc}"]
                }
            duration_ms = int((time.perf_counter() - started) * 1000)

            meta = result.pop("_meta", {}) if isinstance(result, dict) else {}
            engine = meta.get("engine")
            model = meta.get("model")
            note = meta.get("note", note)

            trace_entry = {
                "node": name,
                "label": NODE_LABELS.get(name, name),
                "status": status,
                "engine": engine,
                "model": model,
                "duration_ms": duration_ms,
                "output": meta.get("digest"),
                "note": note,
            }
            result.setdefault("trace", [])
            result["trace"] = [*result.get("trace", []), trace_entry]
            return result

        return wrapper

    return decorator


def get_db(config: dict | None):
    if not config:
        return None
    return (config.get("configurable") or {}).get("db")
