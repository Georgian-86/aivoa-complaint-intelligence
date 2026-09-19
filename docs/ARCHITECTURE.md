# Architecture

This document is the "walk me through your code" companion to the demo video.
It follows one complaint from the analyst's screen to the saved record.

---

## 1. The request

The analyst drops `05_market_complaint_form.pdf` on the intake panel.

`frontend/src/components/intake/AssistantPanel.tsx` → `IntakeSurface.onFiles`
validates the size against the limit the server advertised at
`GET /api/v1/intake/pipeline`, then dispatches:

```ts
dispatch(runIntakeStream({ file }))
```

`runIntakeStream` (`features/intake/intakeSlice.ts`) is a thunk rather than a
plain action because one user gesture produces a *stream* of state
transitions. It calls `streamIntake` in `api/client.ts`, which POSTs a
`FormData` to `/api/v1/intake/stream` and reads the response body with a
`ReadableStream` reader — `EventSource` cannot be used because the request is a
POST carrying a file.

Each SSE frame is parsed and dispatched as a discrete Redux action:

| Event | Action | Effect on the store |
|---|---|---|
| `start` | `stepsAnnounced` | Renders the pipeline rail with every node pending |
| `node`  | `nodeCompleted`  | Marks that node done, advances the next to running, moves the progress bar |
| `complete` | `runCompleted` | Applies the whole result |
| `error` | `runFailed` | Surfaces the message, marks the running node failed |

## 2. The server side of the stream

`backend/app/api/routes/intake.py` → `intake_stream`.

Two details matter:

**The generator owns its own database session.** A FastAPI `Depends(get_db)`
session is closed when the *response* is returned, which for a streaming
response is before the first byte of the body. `_event_stream` therefore opens
a `SessionLocal()` itself and closes it in a `finally`.

**The file is parsed before the stream opens**, so a malformed upload returns a
clean HTTP 422 instead of an error event inside a 200 response.

`services/documents.py` handles the parsing. `pair_orphan_labels` is the
interesting part: PDF text extraction emits one line per visual cell, so a
table row arrives as `Batch No.\nLEV2604A` — two lines, and every label-based
rule misses. The function re-pairs a bare label line with the value beneath it
using a lexicon of ~60 field labels, giving the extractor one canonical shape
whether the source was an e-mail, a Word form or a PDF table.

## 3. The graph

`backend/app/agent/graph.py`. `stream_intake` runs `GRAPH.stream(...,
stream_mode="updates")` and yields one event per node completion.

State is `IntakeState` (`agent/state.py`), a `TypedDict` where `trace` and
`warnings` are `Annotated[list, operator.add]`. That reducer is load-bearing:
`completeness` and `dedupe` execute in the same superstep, and without it the
second branch's update would replace the first's instead of appending.

The database session reaches the nodes through
`config={"configurable": {"db": db}}` — the graph itself stays free of
persistence concerns, which is what makes `run_intake` usable from a test with
no session at all.

### Node by node

**`ingest`** normalises the text and decides whether it is worth reasoning
over: fewer than twelve words and the conditional edge routes straight to
`finalise`. Running a 120B model over "thanks bye" is not free.

**`extract`** is the merge point of the two engines.
`heuristics.extract_fields` runs first and always. If a Groq key is configured,
the extraction model (`openai/gpt-oss-20b` by default — the assignment's
`gemma2-9b-it` was decommissioned by Groq; see `docs/DEPLOYMENT.md`, Step 0)
is asked for the same 18 fields under a strict JSON contract.
`_normalise_llm_fields` coerces types, snaps free text onto the controlled
vocabulary (`_snap_to_enum` — exact, then substring, then token overlap), and
zeroes the confidence of any value it had to discard. `_merge` then applies an
explicit policy, field by field:

- one engine silent → the other wins;
- the field is an identifier (`batch_number`, `customer_contact`,
  `quantity_affected`) and the regex is confident → the regex wins, with
  confidence raised if the model agrees and lowered if it does not;
- otherwise → higher confidence wins.

Finally, any value the analyst has already typed overwrites both and is
stamped `source: "analyst"`. The agent never clobbers a human edit; the UI
enforces the same rule client-side through the `touched` map.

**`completeness`** scores the record against a weighted requirement list drawn
from 21 CFR 211.198(a) and EU GMP Chapter 8, classifying each gap as blocker,
required or recommended, and asks the model to turn the gaps into questions the
analyst can paste into a reply.

**`dedupe`** (`services/similarity.py`) is an explainable weighted scorer over
batch (0.34), product (0.22), defect category (0.20), narrative (0.14),
customer (0.06) and recency (0.04), with a non-linear bonus when batch *and*
defect both match exactly. It returns which components fired, so the UI can say
"matches on identical batch number, same defect category" rather than "87%".
Embeddings would find more and explain less; in a workflow where linking two
records is an auditable decision, that trade goes the other way.

**`classify`** asks the reasoning model (`openai/gpt-oss-120b` by default —
the assignment's `llama-3.3-70b-versatile` is gated to Enterprise-tier Groq
accounts; see `docs/DEPLOYMENT.md`, Step 0) for an ICH Q9-style assessment,
then applies the floor:

```python
if SEVERITY_RANK[rule_severity] > SEVERITY_RANK[risk["severity"]]:
    risk["severity"] = rule_severity
    risk["override"] = "rule_engine_escalation"
```

Regulatory flags are additive — a rule-detected Field Alert Report trigger is
never dropped because the model failed to mention it.

**`analyse`** produces root-cause hypotheses in the 6M categories, a CAPA plan
split into correction / corrective / preventive, and the review-meeting
summary. Every output is validated and clamped before it enters state: unknown
categories are mapped onto the closest known one, likelihoods are clamped to
[0, 1], CAPA types outside the three allowed values become `corrective`.

**`finalise`** flattens the field map into the form payload the Redux store
binds to, and derives `due_date` from severity via `SEVERITY_TAT_DAYS`.

## 4. Back in the browser

`runCompleted` → `applyResult`. The loop that matters:

```ts
for (const [key, field] of Object.entries(result.fields)) {
  if (state.touched[key]) continue          // never clobber a human edit
  if (field.value === null) continue
  state.form[key] = field.value
  state.fields[key] = field                 // keep provenance alongside the value
  landed.push(key)
}
```

`state.form` holds values, `state.fields` holds provenance, `state.touched`
holds authorship. Keeping them separate is what lets the UI render a
confidence badge next to a value, flash newly-arrived fields, and re-run the
assessment without losing the analyst's corrections.

The `Field` component in `ComplaintForm.tsx` subscribes to exactly three slices
of state for its own name, so typing in one field does not re-render the other
seventeen.

## 5. Persistence

`POST /api/v1/complaints` writes the record, allocates a human-readable
reference (`CMP-2026-0009`), links the `AgentRun` row that produced it, and
appends two `AuditEvent` rows — one for the human action, one attributed to
`intake-agent` with `actor_type="agent"`.

That last distinction is the point. The audit trail separates what the analyst
did from what the machine proposed, so a year later it is still possible to
answer "who decided this was Critical, and on what evidence".

---

## Data model

```
complaints ─┬─< agent_runs ──< agent_node_traces
            └─< audit_events
copilot_messages (thread-scoped, optionally linked to a complaint)
```

`complaints.ai_payload` snapshots the full assessment — risk, gaps, duplicates,
root causes, CAPA — as it stood at intake. The record stays self-describing
even if the prompts, the models or the rules change afterwards, which is the
whole reason a regulated system versions its evidence rather than recomputing it.

## Configuration

Everything is environment-driven (`app/core/config.py`) so one image promotes
across dev → qualification → production without a rebuild. `DATABASE_URL`
alone switches SQLite → Postgres → MySQL; nothing else in the code branches on
the dialect.
