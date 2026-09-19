"""Duplicate / recurrence detection against the complaint register."""

from __future__ import annotations

from typing import Any

from app.agent.nodes._base import get_db, traced
from app.services.similarity import find_duplicates


@traced("dedupe")
def dedupe(state: dict, config: dict | None = None) -> dict[str, Any]:
    db = get_db(config)
    if db is None:
        return {"duplicates": [], "_meta": {"engine": "deterministic",
                                            "note": "No database session on this run.",
                                            "digest": {"matches": 0}}}

    fields = state.get("fields") or {}
    form = {k: (v or {}).get("value") for k, v in fields.items()}
    matches = find_duplicates(db, form)

    warnings: list[str] = []
    if matches and matches[0]["score"] >= 0.85:
        warnings.append(
            f"Likely duplicate of {matches[0]['reference']} "
            f"({int(matches[0]['score'] * 100)}% match) — confirm before logging a new record."
        )

    return {
        "duplicates": matches,
        "warnings": warnings,
        "_meta": {
            "engine": "deterministic",
            "digest": {
                "matches": len(matches),
                "top_score": matches[0]["score"] if matches else 0,
                "top_reference": matches[0]["reference"] if matches else None,
            },
        },
    }
