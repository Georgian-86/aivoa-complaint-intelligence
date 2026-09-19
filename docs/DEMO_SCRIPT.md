# Demo video script

Two videos are required. Total 5–10 minutes. Record at 1440p or higher; the UI
is dense and text must stay legible.

Before recording: put a real `GROQ_API_KEY` in `backend/.env` and restart the
API, so the rail reads "Groq inference live". Delete `backend/aivoa.db` first
so the register reseeds cleanly.

---

## Video 1 — Working demonstration (≈3 min)

**0:00 Frame the problem.** "A market complaint arrives as an e-mail or a PDF.
Today a QA analyst re-types it into the QMS, decides the severity from memory,
and hopes someone notices it is the third one this quarter on the same batch.
This is the intake module that does that work with them."

**0:20 Show the empty form.** Point out the four sections matching a real
complaint record, and the document-control strip — this is a controlled record,
not a web form.

**0:35 Drop `samples/01_particulate_injection_email.txt`.** Do not narrate over
the extraction — let the pipeline rail run. Then walk it: seven nodes, engine
badge per node, latency per node.

**1:05 The form filled itself.** Hover a confidence badge — show the verbatim
sentence behind the value. Hover a low-confidence one and say why that matters:
the analyst has to be able to challenge the machine.

**1:25 The verdict strip.** Critical, 90/100, Severe, three regulatory
triggers. Scroll to the full assessment.

**1:40 Walk the six assessment cards:**
- Risk: the weighted drivers, each tied to a quote from the source
- Regulatory reportability: FAR and recall assessment, with the citation
- Completeness: what is missing and the questions to send the complainant
- **Duplicates: this is the moment.** It has found two earlier complaints on
  the same product and defect. Open one.
- Root cause: three hypotheses, each with the record to pull next
- CAPA: correction / corrective / preventive, with effectiveness checks

**2:30 Correct something.** Change a field, show the badge flip to "YOU", hit
Re-assess, and point out that the agent did not overwrite the edit.

**2:45 Save.** Show the reference number, open the register, open the record —
audit trail and persisted agent trace. Then the dashboard: severity mix, and
the recurrence watchlist that caught the repeat.

---

## Video 2 — Code walkthrough (≈5 min)

Follow one complaint end to end. `docs/ARCHITECTURE.md` is this script in prose.

**0:00 `AssistantPanel.tsx`** — the drop handler dispatches `runIntakeStream`.
Say why it is a thunk: one gesture, a stream of state transitions.

**0:30 `api/client.ts` → `streamIntake`** — POST + manual `ReadableStream`
reader, because `EventSource` cannot carry a file. Show the frame parser.

**1:00 `intakeSlice.ts`** — three parallel maps: `form` holds values, `fields`
holds provenance, `touched` holds authorship. Show `applyResult` skipping
touched keys. This is the "machine proposes, human disposes" rule in code.

**1:40 `routes/intake.py` → `_event_stream`** — the generator owns its own
session, because a `Depends` session closes before the first byte of a
streaming body.

**2:00 `services/documents.py` → `pair_orphan_labels`** — open
`samples/05_market_complaint_form.pdf`, show that PDF extraction puts "Batch
No." and "LEV2604A" on separate lines, and that this function re-pairs them.

**2:30 `agent/graph.py`** — draw the graph. Point at the conditional edge out of
`ingest`, the fan-out to `completeness` and `dedupe`, the fan-in at `classify`,
and the `operator.add` reducer in `state.py` that makes the merge safe.

**3:20 `nodes/extract.py` → `_merge`** — the field-by-field policy between the
two engines. Model wins on prose, regex wins on identifiers, analyst wins over
both.

**4:00 `nodes/classify.py`** — the safety floor. Read the override block aloud
and say the line that justifies it: over-classifying costs an investigation,
under-classifying costs a recall that never happened.

**4:30 `services/similarity.py`** — the weighted scorer, and why it is lexical
rather than embedding-based: a reviewer must be able to justify the link.

**4:50 Close on the trade you would revisit.** Suggested: the deterministic
fallback is a floor, not a peer, and the next thing to build is a golden-set
evaluation harness so prompt changes have to pass a regression bar.

---

## Things to say out loud

The panel is checking whether you understand your own code. Say these:

- Why LangGraph rather than a chain: conditional routing, a fan-out that
  actually runs in parallel, and a durable trace per node.
- Why two models: a small, fast model (`openai/gpt-oss-20b`) is cheap enough
  for extraction on every upload; reasoning about patient safety gets the
  larger one (`openai/gpt-oss-120b`).
- Why those specific models and not the ones named in the brief: the brief
  names `gemma2-9b-it` and `llama-3.3-70b-versatile`. Mid-build, Groq
  decommissioned `gemma2-9b-it` outright and moved `llama-3.3-70b-versatile`
  behind an Enterprise-tier plan — both confirmed against a live key, not
  assumed. `EXTRACTION_MODEL`/`REASONING_MODEL` are env vars specifically so
  that swap cost one line each, not a redeploy. That is the actual point to
  make: a spec that names a specific third-party model can go stale before
  you ship, and the fix is to make the model configurable, not to hardcode
  around today's catalog.
- Why the regex layer survives even with a good model: small models transpose
  characters in batch codes, and a wrong lot number sends an investigator to
  the wrong batch record.
- Why every value carries evidence: "the AI said so" is not a defence in front
  of an inspector.
- What you would fix first, unprompted.
