# AIVOA — AI Customer Complaint Management

An AI-assisted customer complaint intake and triage system for GMP-regulated
pharmaceutical manufacturing (API and finished dosage form).

An analyst drops in a complaint e-mail or PDF. A **LangGraph** agent reads it,
populates the complaint record field by field — each value carrying a
confidence score and the verbatim sentence it came from — classifies the GMP
severity, checks the record against what 21 CFR 211.198 actually requires,
searches the register for duplicates, and proposes root-cause hypotheses and a
CAPA plan. The analyst reviews, corrects and saves. **The machine proposes; the
human signs.**

---

## Quick start

Two terminals, no Docker, no API key needed.

```bash
# ── Terminal 1: backend ───────────────────────────────────────────────
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional: paste your Groq key
uvicorn app.main:app --reload                          # http://127.0.0.1:8000/docs

# ── Terminal 2: frontend ──────────────────────────────────────────────
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

The register seeds itself with eight reference complaints on first run, so the
dashboard and the duplicate detector have something to work with immediately.

Once a Groq key is configured, verify it before anything else:

```bash
curl http://127.0.0.1:8000/api/v1/health/llm
```

That endpoint makes one real call per model and reports latency, or the exact
upstream error if a model has been decommissioned. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for hosting and the full
what-is-still-missing list.

**With Docker** (Postgres + API + nginx):

```bash
cp .env.example .env     # paste GROQ_API_KEY if you have one
docker compose up --build
# → http://localhost:8080
```

### Groq API key

Create one at <https://console.groq.com/keys> and put it in `backend/.env`:

```
GROQ_API_KEY=gsk_...
EXTRACTION_MODEL=openai/gpt-oss-20b
REASONING_MODEL=openai/gpt-oss-120b
```

The assignment names `gemma2-9b-it` and `llama-3.3-70b-versatile`. Groq has
since decommissioned the former outright and gated the latter to
Enterprise-tier accounts (both verified against a live key while building
this) — see `docs/DEPLOYMENT.md`, Step 0, for the evidence and how to switch
back if your Groq account has access to the originally-named models.

**Without a key the application still works end to end.** Every agent node
falls back to a deterministic rule engine, the UI says so plainly in the
navigation rail and on every run, and extraction quality drops but nothing
breaks. That was a deliberate design decision: a reviewer should be able to
clone the repository and see the whole workflow without first provisioning
credentials.

### Try it

`samples/` contains five realistic complaints, none of them real:

| File | Shape | What it exercises |
|---|---|---|
| `01_particulate_injection_email.txt` | Distributor e-mail | Critical path — patient harm, sterile route, duplicate of a seeded record |
| `02_labelling_error_letter.txt` | Formal letter | Labelled key/value block, narrow-therapeutic-index reasoning |
| `03_minor_packaging_email.txt` | Consumer e-mail, unstructured | Minor classification, sparse record, completeness gaps |
| `04_api_oos_email.txt` | CDMO notification | Bulk API, OOS assay, retest date rather than expiry |
| `05_market_complaint_form.pdf` | PDF form | Tabular PDF where labels and values land on separate lines |

---

## Technology

| Layer | Choice |
|---|---|
| Frontend | React 18 + **Redux Toolkit** + TypeScript, Vite, React Router |
| Backend | **Python** + **FastAPI**, SQLAlchemy 2.0, Pydantic v2 |
| Agent | **LangGraph** — stateful graph, conditional routing, fan-out/fan-in |
| LLM | **Groq** — `openai/gpt-oss-20b` for extraction, `openai/gpt-oss-120b` for reasoning (assignment names `gemma2-9b-it` / `llama-3.3-70b-versatile`; see `docs/DEPLOYMENT.md`) |
| Database | **PostgreSQL** (Docker) / SQLite (zero-setup dev), MySQL supported |
| Typeface | **Inter** |

No chart library, no icon library, no component library. The visual system is
in `frontend/src/styles/tokens.css` and the icons are 28 hand-drawn glyphs in
`frontend/src/components/Icon.tsx`.

---

## The agent

```
                      ┌──────────────┐
                      │   ingest     │  normalise · usability gate
                      └──────┬───────┘
                   unusable  │  usable            ← conditional edge
              ┌──────────────┴───────────────┐
              ▼                              ▼
         ┌─────────┐                   ┌──────────┐
         │finalise │                   │ extract  │  gpt-oss-20b + regex guardrail
         └─────────┘                   └────┬─────┘
                                            │ fan-out (one superstep)
                             ┌──────────────┴──────────────┐
                             ▼                             ▼
                     ┌──────────────┐              ┌──────────────┐
                     │ completeness │              │    dedupe    │
                     └──────┬───────┘              └──────┬───────┘
                            └──────────────┬──────────────┘
                                           ▼  fan-in
                                    ┌──────────────┐
                                    │   classify   │  gpt-oss-120b + rule floor
                                    └──────┬───────┘
                                           ▼
                                    ┌──────────────┐
                                    │   analyse    │  root cause · CAPA · summary
                                    └──────┬───────┘
                                           ▼
                                    ┌──────────────┐
                                    │   finalise   │
                                    └──────────────┘
```

`completeness` and `dedupe` depend only on `extract` and not on each other, so
they are declared as a fan-out and LangGraph runs them in the same superstep,
joining before `classify`. The `trace` and `warnings` channels use
`operator.add` reducers so the two branches merge without clobbering each other.

Each node is wrapped by a `@traced` decorator that records its duration, the
engine that served it and a compact digest of its output. That trace streams to
the browser over SSE while the run is in flight, and is persisted to
`agent_node_traces` afterwards — so a complaint saved six months ago can still
show exactly how the machine reached its conclusion.

### Three decisions worth defending

**1. The LLM is not the only engine — it is the preferred one.**
Every node has a deterministic counterpart. They are *merged*, not switched:
the model wins on prose (description, rationale, hypotheses), the regex layer
wins on identifiers (batch codes, dates, e-mail addresses) where a small model
routinely transposes a character. Where both agree, confidence is raised; where
they disagree on an identifier, the literal match wins and the disagreement is
visible in the field's confidence badge.

**2. There is a safety floor the model cannot lower.**
If the rule engine detects a patient-harm signal — hospitalisation, sterility
failure, product mix-up, a sterile route — and the model returned something
softer, the rule wins, the record is escalated, and the override is surfaced in
the UI and written to the trace. Over-classifying a complaint costs an
investigation. Under-classifying one costs a recall that never happened. Those
are not symmetric errors, and the system is not symmetric about them.

**3. Every machine-written value carries its provenance.**
`{value, confidence, evidence, source}`, not a bare string. The UI renders a
three-bar confidence meter beside every AI-populated field; hovering shows the
verbatim sentence the value came from. In a regulated workflow an analyst has
to be able to challenge the machine, and "the AI said so" is not a defence in
front of an inspector.

---

## Features

### Core workflow
- Drag-and-drop or paste intake — PDF, DOCX, TXT, MD, EML, MSG, HTML
- Live extraction rail: each agent node reports as it completes, with timings
  and the model that served it
- Four-section complaint form matching the reference UI, with field-level
  confidence and evidence
- Conversational assistant that answers from the record and can *propose* field
  changes the analyst applies with one click
- Complaint register with search, faceting, sorting and pagination
- Record detail with the full audit trail and the agent trace that produced it

### Bonus AI features
| Feature | Where |
|---|---|
| **Complaint Completeness Checker** | Weighted score against 21 CFR 211.198(a) plus blocker/required/recommended gaps |
| **AI Risk Classification** | ICH Q9-style composite 0–100 score, four bands, weighted drivers each tied to evidence |
| **Duplicate Complaint Detection** | Explainable weighted scorer over batch, product, defect, narrative and recency — no black-box embeddings |
| **Root Cause Recommendation** | 2–4 ranked hypotheses in 6M categories, each naming the record or test that confirms or kills it |
| **CAPA Recommendation** | Separated into correction / corrective / preventive, each with an owner function and an effectiveness check |
| **Complaint Summary** | One dense paragraph for the QA review meeting |
| **Regulatory reportability** | Field Alert Report, adverse-event, recall-assessment and authority-notification triggers, each with its citation |
| **Recurrence watchlist** | Products attracting the same defect more than once — the trend signal GMP actually asks for |
| **Clarifying questions** | Ready-to-send questions for the complainant, generated from the actual gaps |

---

## Project layout

```
backend/
  app/
    agent/            LangGraph pipeline
      graph.py        graph assembly, sync + streaming entry points
      nodes/          one module per node
      prompts.py      prompt library
      llm.py          Groq client, JSON coercion, graceful degradation
    api/routes/       intake · complaints · copilot · analytics · health
    services/
      taxonomy.py     the domain vocabulary — one source of truth
      heuristics.py   deterministic extraction and risk engine
      documents.py    PDF / DOCX / EML parsing and label pairing
      similarity.py   explainable duplicate scorer
    models/           SQLAlchemy — complaints, agent runs, traces, audit
  tests/              40 tests, no network required
frontend/
  src/
    features/         Redux slices: intake · complaints · copilot · system
    components/       shell, form, assistant, assessment, primitives
    pages/            intake · register · detail · dashboard
    styles/tokens.css the design system
samples/              five realistic complaints (four text, one PDF)
docs/                 architecture, design, deployment and demo notes
scripts/              one-command push to GitHub
.github/workflows/    CI: pytest, typecheck, build, Docker
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # 52 passed
cd frontend && npm run typecheck && npm run build
```

CI runs all three on every push (`.github/workflows/ci.yml`), plus a build of
both Docker images.

The tests run without a Groq key and without network access — they exercise the
deterministic engine, the graph topology (including that unusable input
short-circuits past extraction, and that the fan-out branches both merge), the
safety floor, and the HTTP contract.

---

## Limitations, stated honestly

- **OCR is out of scope**, as the brief allows. A scanned PDF with no text
  layer is detected and reported to the analyst rather than silently returning
  an empty record.
- **No authentication.** A real QMS needs named users and electronic signatures
  under 21 CFR Part 11. The audit trail is modelled with an `actor` and an
  `actor_type` so that it can be attached, but this build has no login.
- **The deterministic fallback is a floor, not a peer.** It reads structured and
  semi-structured complaints well; free-form narrative without labels degrades
  it. Configure a Groq key for real extraction quality.
- **Duplicate detection is lexical**, deliberately: a QA reviewer must be able
  to justify why two records were linked. Semantic search would find more
  matches and explain fewer of them.
- **Seed data is fictional.** No real product, batch, company or person appears
  anywhere in this repository.

---

## Attribution

Built for the AIVOA Round 1 AI Product Engineer assignment. AI tooling was used
throughout, as the brief encourages; the architecture, the domain model, the
merge policy between the two engines, the safety floor and the design system
are deliberate choices, and every one of them is explained above or in
`docs/ARCHITECTURE.md`.
