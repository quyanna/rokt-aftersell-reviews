#!/usr/bin/env bash
# Runs the whole pipeline. Every stage is incremental, so this is safe to re-run:
# nothing re-downloads or re-classifies work already done.
#
# Needs uv (https://docs.astral.sh/uv/) and, from stage 3 on, an Anthropic API key
# in .env as ANTHROPIC_API_KEY=... or exported in your shell.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/6  fetching review pages =="        && uv run fetch.py
echo "== 2/6  parsing into SQLite =="          && uv run parse.py
echo "== 3/6  classifying reviews =="          && uv run classify.py
echo "== 4/6  verifying every quote and name ==" && uv run verify.py
echo "== 5/6  checking the documentation =="   && uv run docs_match.py
echo "== 6/6  building the triage sheet =="    && uv run report.py

echo
echo "Done. Open triage-sheet.html"
echo "To check the classifications by hand: uv run sample.py"
