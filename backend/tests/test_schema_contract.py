"""Regression tests for the extract/schema contract.

``app.agent.nodes.extract._merge`` can stamp a field's source as
``"llm+regex"`` (both engines agreed on an identifier) or ``"analyst"`` (a
human edit overwrote both, on the /intake/reassess path). Both values only
ever appear once the LLM is actually live, or once an analyst edit has
round-tripped through the API -- neither happens under the
``GROQ_API_KEY=""`` deterministic mode every other test in this suite runs
under. That gap is exactly how both values went missing from
``app.schemas.intake.ExtractedField``'s ``source`` literal for a time without
anything catching it: the pipeline only surfaced the mismatch as a 500 the
first time a real Groq key produced an agreeing field. These tests pin the
contract directly, without a network call.
"""

from __future__ import annotations

import pytest

from app.agent.nodes.extract import REGEX_PREFERRED, _merge
from app.schemas.intake import ExtractedField


class TestExtractedFieldSourceContract:
    """Every value `_merge` (or the reassess path) can put in `source` must
    validate against the API's own response schema."""

    @pytest.mark.parametrize(
        "source", ["llm", "heuristic", "regex", "llm+regex", "analyst", "default", "none"]
    )
    def test_every_real_source_value_validates(self, source):
        field = ExtractedField(value="x", confidence=0.9, evidence=None, source=source)
        assert field.source == source


class TestMergeSourceTagging:
    def _field(self, value, confidence, source):
        return {"value": value, "confidence": confidence, "evidence": None, "source": source}

    def test_agreeing_identifier_is_tagged_llm_and_regex(self):
        key = next(iter(REGEX_PREFERRED))
        llm_fields = {key: self._field("CFX24B902", 0.9, "llm")}
        regex_fields = {key: self._field("CFX24B902", 0.85, "regex")}

        merged = _merge(llm_fields, regex_fields)

        assert merged[key]["source"] == "llm+regex"
        # And that exact value must still validate against the API schema --
        # this is the assertion that would have caught the original bug.
        ExtractedField(**merged[key])

    def test_disagreeing_identifier_keeps_the_regex_literal(self):
        key = next(iter(REGEX_PREFERRED))
        llm_fields = {key: self._field("CFX24B903", 0.9, "llm")}
        regex_fields = {key: self._field("CFX24B902", 0.85, "regex")}

        merged = _merge(llm_fields, regex_fields)

        assert merged[key]["source"] == "regex"
        ExtractedField(**merged[key])
