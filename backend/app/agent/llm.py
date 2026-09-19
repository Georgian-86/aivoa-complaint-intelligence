"""Groq LLM access layer.

Responsibilities
----------------
1. Hold one lazily-constructed client per model so we do not pay handshake
   cost on every node.
2. Force *strict JSON* out of the model and repair the common failure modes
   (fenced code blocks, trailing prose, single quotes, trailing commas).
   Small instruction-tuned models such as the default extraction model
   (``openai/gpt-oss-20b`` -- see ``core.config.Settings``) are perfectly
   capable of structured output but need this seatbelt.
3. Degrade gracefully. If no GROQ_API_KEY is configured — or the API errors —
   we raise ``LLMUnavailable`` and the calling node falls back to the
   deterministic engine rather than failing the whole intake.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_FIRST_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class LLMUnavailable(RuntimeError):
    """Raised when the model cannot be reached or returned nothing usable."""


def _coerce_json(raw: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from a chat completion."""
    if not raw or not raw.strip():
        raise LLMUnavailable("empty completion")

    candidates: list[str] = []
    fenced = _JSON_FENCE.search(raw)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(raw)
    blob = _FIRST_OBJECT.search(raw)
    if blob:
        candidates.append(blob.group(0))

    for candidate in candidates:
        text = candidate.strip()
        for attempt in (text, _TRAILING_COMMA.sub(r"\1", text)):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    raise LLMUnavailable(f"model did not return JSON (got {raw[:180]!r})")


class LLMClient:
    """Thin façade over ``langchain_groq.ChatGroq``."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._import_error: str | None = None

    # ── availability ─────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return settings.llm_enabled

    def _model(self, name: str, temperature: float | None, json_mode: bool):
        key = f"{name}:{temperature}:{json_mode}"
        if key in self._cache:
            return self._cache[key]
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:  # pragma: no cover - dependency guard
            self._import_error = str(exc)
            raise LLMUnavailable(f"langchain-groq not installed: {exc}") from exc

        kwargs: dict[str, Any] = {
            "model": name,
            "api_key": settings.groq_api_key,
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": 0,  # retries are orchestrated here, not in the SDK
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        client = ChatGroq(**kwargs)
        self._cache[key] = client
        return client

    # ── calls ────────────────────────────────────────────────────────────────
    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        if not self.enabled:
            raise LLMUnavailable("GROQ_API_KEY is not configured")
        target = model or settings.extraction_model
        client = self._model(target, temperature, json_mode=False)
        last: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            try:
                response = client.invoke(
                    [("system", system), ("human", user)]
                )
                return (response.content or "").strip()
            except Exception as exc:  # noqa: BLE001 - surfaced as LLMUnavailable
                last = exc
                logger.warning("groq call failed (attempt %s/%s): %s",
                               attempt + 1, settings.llm_max_retries + 1, exc)
        raise LLMUnavailable(str(last))

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call the model and guarantee a ``dict`` back (or raise)."""
        if not self.enabled:
            raise LLMUnavailable("GROQ_API_KEY is not configured")
        target = model or settings.extraction_model

        last: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            # First attempt uses native JSON mode; a retry drops it in case the
            # model/endpoint rejects response_format.
            json_mode = attempt == 0
            try:
                client = self._model(target, temperature, json_mode=json_mode)
                response = client.invoke([("system", system), ("human", user)])
                return _coerce_json(response.content or "")
            except Exception as exc:  # noqa: BLE001
                last = exc
                logger.warning(
                    "groq json call failed (model=%s attempt=%s): %s", target, attempt + 1, exc
                )
        raise LLMUnavailable(str(last))


llm = LLMClient()
