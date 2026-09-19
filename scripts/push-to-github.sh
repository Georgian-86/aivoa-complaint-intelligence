#!/usr/bin/env bash
# Same as push-to-github.ps1, for Git Bash / WSL / macOS / Linux.
#
#   ./scripts/push-to-github.sh                                   # uses the gh CLI
#   ./scripts/push-to-github.sh https://github.com/<you>/aivoa.git  # explicit remote
set -euo pipefail

REPO_NAME="${REPO_NAME:-aivoa-complaint-intelligence}"
REMOTE_URL="${1:-}"
VISIBILITY="${VISIBILITY:-public}"
DESCRIPTION="AI-assisted customer complaint intake and triage for GMP-regulated pharmaceutical manufacturing. FastAPI + LangGraph + Groq + React/Redux."

cd "$(dirname "$0")/.."

command -v git >/dev/null || { echo "git is not installed."; exit 1; }
[ -f README.md ] && [ -d backend ] || { echo "Not the AIVOA project root."; exit 1; }

# git refuses to commit without an identity.
if ! git config --global user.name >/dev/null; then
  read -rp "Your name (for commit authorship): " GIT_NAME
  git config --global user.name "$GIT_NAME"
fi
if ! git config --global user.email >/dev/null; then
  read -rp "Your GitHub e-mail address: " GIT_EMAIL
  git config --global user.email "$GIT_EMAIL"
fi

echo "==> Preparing the local repository"
[ -d .git ] || git init -q

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "AIVOA complaint intelligence: LangGraph intake agent, FastAPI backend, React/Redux UI" \
    -m "AI-assisted customer complaint intake and triage for GMP-regulated API and finished-dosage-form manufacturing.

- LangGraph pipeline: conditional routing, fan-out/fan-in, per-node trace streamed over SSE and persisted for audit
- Groq gemma2-9b-it for extraction, llama-3.3-70b-versatile for reasoning, with a deterministic engine that keeps the product working without a key
- Field-level provenance: every extracted value carries confidence, source and the verbatim evidence it came from
- Deterministic safety floor the model cannot lower on patient-safety signals
- Explainable duplicate detection, completeness checking against 21 CFR 211.198(a), root-cause hypotheses and CAPA recommendations
- React 18 + Redux Toolkit, bespoke design system, 43 backend tests"
  echo "    Committed."
else
  echo "    Nothing new to commit."
fi

git branch -M main

echo "==> Configuring the remote"
if [ -n "$REMOTE_URL" ]; then
  git remote get-url origin >/dev/null 2>&1 \
    && git remote set-url origin "$REMOTE_URL" \
    || git remote add origin "$REMOTE_URL"
elif git remote get-url origin >/dev/null 2>&1; then
  echo "    origin already set -> $(git remote get-url origin)"
elif command -v gh >/dev/null; then
  gh auth status >/dev/null 2>&1 || gh auth login
  gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --description "$DESCRIPTION"
else
  cat <<'MSG'

    No remote configured and the GitHub CLI is not installed.
    Create an EMPTY repository at https://github.com/new, then re-run:

        ./scripts/push-to-github.sh https://github.com/<your-username>/aivoa-complaint-intelligence.git

MSG
  exit 1
fi

echo "==> Pushing to GitHub"
git push -u origin main
echo
echo "    Done. $(git remote get-url origin | sed 's/\.git$//')"
