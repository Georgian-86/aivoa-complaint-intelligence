# Deployment

Three questions decide everything here: where the API runs, where Postgres
lives, and where the static frontend is served from. Everything else is
configuration.

---

## 0. Before anything: the Groq key, and the model substitution it forced

**Resolved.** The LLM path has now run against a live key, and the assignment's
two named models do not work on it:

| Assignment names | Live result against a real key | Meaning |
|---|---|---|
| `gemma2-9b-it` | `HTTP 400 model_decommissioned` | Groq removed it entirely. Not tier-gated -- gone for every account. |
| `llama-3.3-70b-versatile` | `HTTP 404 model_not_found` | Listed in Groq's docs as an Enterprise-tier model; not reachable on a standard key. |

Both were confirmed by calling the Groq chat-completions API directly with a
real key, not inferred from documentation. The project now defaults to:

```
EXTRACTION_MODEL=openai/gpt-oss-20b     # fast, small -- runs on every upload
REASONING_MODEL=openai/gpt-oss-120b     # larger -- risk, RCA, CAPA, summary
```

both confirmed working end to end (auth, JSON mode, and a full intake run)
against a live key. This is a genuine substitution, not a downgrade of intent:
the assignment's own shape -- a cheap model for extraction, a larger one for
reasoning-heavy nodes -- is preserved; only the specific model names changed
because the vendor's catalog moved after the brief was written. Both remain
plain environment variables (`EXTRACTION_MODEL` / `REASONING_MODEL` in
`backend/.env`, or the Render blueprint's env vars in production) specifically
so this doesn't require a code change if your Groq account can reach the
originally-named models, or if Groq's catalog moves again.

One implementation detail worth knowing if you touch `app/agent/llm.py`:
`openai/gpt-oss-*` are reasoning models that spend a chunk of their completion
budget on hidden chain-of-thought before the visible answer -- in testing,
`gpt-oss-20b` used ~60 reasoning tokens and `gpt-oss-120b` ~220 even for a
one-line reply. `llm.py` does not set `max_tokens`, so this does not truncate
output, but it does add latency; if you ever add an explicit `max_tokens` cap,
budget for the reasoning tokens on top of the JSON you actually want back.

To verify any of this yourself:

1. Put your key in `backend/.env`:

   ```
   GROQ_API_KEY=gsk_...
   ```

2. Restart the API and hit the probe:

   ```
   curl http://127.0.0.1:8000/api/v1/health/llm
   ```

   It makes one real call per configured model and reports latency, or the
   exact upstream error. If a model ever reports `decommissioned` or
   `model_not_found` again, open <https://console.groq.com/docs/models>,
   pick current models, and update `EXTRACTION_MODEL` / `REASONING_MODEL`
   accordingly -- note the substitution here and in the README rather than
   quietly changing it, the way this one is documented.

3. Re-run each sample in `samples/` with the key live and compare against the
   deterministic output. The model should beat the rule engine on
   `description`, `complaint_type` and the risk rationale. If it does not, the
   prompt needs work, not the code.

---

## 1. Local, exactly as a reviewer will run it

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt && uvicorn app.main:app --reload

cd frontend && npm install && npm run dev
```

## 2. Docker, single host

```bash
cp .env.example .env          # paste GROQ_API_KEY
docker compose up --build     # → http://localhost:8080
```

This is the configuration to demo from: Postgres, the API and nginx serving the
built bundle, all on one network, with the SPA and the API on one origin so
Server-Sent Events work without CORS.

## 3. Public hosting

This repo ships two blueprint files so the actual click-through is short once
the code is on GitHub — neither service needs configuration typed by hand:

| Piece | File | What happens |
|---|---|---|
| API + Postgres | `render.yaml` (repo root) | Render dashboard -> **New -> Blueprint** -> pick this repo. Render reads the file, provisions a free Postgres instance, builds `backend/Dockerfile`, and wires `DATABASE_URL` between them automatically. It asks once for `GROQ_API_KEY` (leave blank to run the deterministic engine). |
| Frontend | `frontend/vercel.json` | Vercel dashboard -> **Add New -> Project** -> import this repo, root directory `frontend`. Vite is auto-detected. |

Order matters: deploy the API first so you have its `https://aivoa-api-....onrender.com`
URL, then:

1. Open `frontend/vercel.json` and replace `REPLACE-WITH-YOUR-RENDER-URL` with
   that URL (the `/api/*` rewrite proxies the SPA's same-origin `/api/v1`
   calls to it, so `VITE_API_BASE` never needs to change and SSE keeps working
   without a CORS preflight). Commit and Vercel redeploys automatically.
2. On Render, set the API's `CORS_ORIGINS` env var to the Vercel domain
   (`https://<project>.vercel.app`) as a defense-in-depth belt to the
   same-origin rewrite above, then redeploy the API.

Prefer to wire the two independently instead (no rewrite, separate origins)?
Set `VITE_API_BASE` to the full API URL (`https://aivoa-api-....onrender.com/api/v1`)
as a Vercel project environment variable instead of editing `vercel.json`, and
make sure `CORS_ORIGINS` on the API matches the Vercel domain exactly.

Three things break on first deploy, every time:

**CORS.** `CORS_ORIGINS` must contain the exact frontend origin, scheme
included. The regex in `main.py` only covers localhost.

**SSE through a proxy.** `/api/v1/intake/stream` must not be buffered. nginx
needs `proxy_buffering off` (already in `frontend/nginx.conf`); Cloudflare
needs the route excluded from caching; some platform load balancers need
response buffering disabled explicitly. If the extraction rail jumps straight
from empty to complete, buffering is the cause.

**Cold starts.** A free-tier API container that sleeps will make the first
upload look broken. Either pay for an always-on instance for the demo, or warm
it before recording.

### Production settings to change

```
ENVIRONMENT=production
DEBUG=false                      # stops error hints leaking into responses
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=https://your-frontend-domain
```

`Base.metadata.create_all()` at startup is fine for a demo and wrong for
production — the moment the schema changes under real data you need Alembic
migrations instead.

---

## What is still missing before this is a real product

Ordered by what a reviewer or a first user will hit first.

### Blocking
1. **Verify the LLM path end to end** (above). Everything else is secondary.
2. **Authentication and named users.** The audit trail already carries `actor`
   and `actor_type`; there is no login to populate them. Any regulated
   deployment needs this plus electronic signatures under 21 CFR Part 11.
3. **Alembic migrations.** `create_all` cannot alter a live table.

### Important
4. **An evaluation harness.** ~50 annotated complaints scored per field for
   extraction accuracy and per record for severity agreement, run in CI, so a
   prompt edit has to pass a regression bar instead of a vibe check.
5. **Frontend tests.** `intakeSlice` holds the rule that matters most — the
   agent never overwrites an analyst edit — and nothing asserts it. Vitest plus
   React Testing Library on the reducers is an afternoon.
6. **SQL aggregation in analytics.** `/analytics/overview` loads every
   complaint into memory. Correct at 8 records, unusable at 100k.
7. **Partial re-assessment.** `POST /intake/reassess` re-runs the whole graph
   including an extraction it discards. It should enter at `classify`.
8. **Rate limiting and request guards** on the intake endpoints — an
   unauthenticated upload endpoint that calls a paid API is an invitation.

### Worth doing
9. **Streaming copilot replies** — it blocks today.
10. **Structured logging with a request id**, so one intake run is greppable
    across the API and the agent trace.
11. **Error tracking** (Sentry or equivalent) on both halves.
12. **Pagination on audit events and agent traces** for long-lived records.
13. **Human-in-the-loop interrupts** using LangGraph checkpointing, so a
    Critical classification can pause for reviewer confirmation before the
    CAPA node runs.
14. **The investigation module.** Intake stops at triage; the record still
    needs investigation, effectiveness check and closure approval.
