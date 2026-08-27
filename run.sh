#!/usr/bin/env bash
# Runs the whole pipeline. Every stage is incremental, so this is safe to re-run:
# nothing re-downloads or re-classifies work already done.
#
# Needs uv (https://docs.astral.sh/uv/) and, from stage 3 on, an Anthropic API key
# in .env as ANTHROPIC_API_KEY=... or exported in your shell.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/7  fetching review pages =="        && uv run fetch.py
echo "== 2/7  parsing into SQLite =="          && uv run parse.py
echo "== 3/7  classifying reviews =="          && uv run classify.py
echo "== 4/7  verifying every quote and name ==" && uv run verify.py
echo "== 5/7  checking the documentation =="   && uv run docs_match.py
echo "== 6/7  building the triage sheet =="    && uv run report.py
echo "== 7/7  building the data page =="       && uv run data_page.py

echo
echo "Done. Open docs/index.html (data.html sits alongside it)"
echo "To check the classifications by hand: uv run sample.py"
