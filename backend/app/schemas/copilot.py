from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CopilotRequest(BaseModel):
    thread_id: str
    message: str = Field(min_length=1)
    form: dict[str, Any] = Field(default_factory=dict)
    source_text: str | None = None
    complaint_id: str | None = None


class CopilotAction(BaseModel):
    """A structured patch the assistant proposes for the form.

    The assistant never mutates the record directly; it proposes, the analyst
    accepts. That keeps the human accountable, which is the whole point in a
    regulated workflow.
    """

    field: str
    value: Any
    reason: str | None = None


class CopilotResponse(BaseModel):
    reply: str
    engine: str
    model: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    actions: list[CopilotAction] = Field(default_factory=list)
