# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Checks every claim the classifier made against the review it came from.

This exists so that "how do you know?" has a mechanical answer for every row
rather than a verbal one. It proves nothing about whether a judgement is correct,
which no automated check could. What it proves is narrower and still worth having:
that nothing was invented.

Three checks run:

  1. Every extracted staff name appears in the review text.
  2. Every evidence quote is a literal span of the review text.
  3. Every row that carries a resolvability also carries a reason, and every
     row with a decided resolvability carries a quote.

Any row failing any check is printed in full so it can be looked at.

Usage:
    uv run verify.py
"""

import json
import re
import sqlite3
import sys
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "reviews.db"


def normalise(text):
    """Collapse whitespace so a quote spanning a line break still matches."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def main():
    db = sqlite3.connect(DB_PATH)
    rows = db.execute(
        """
        SELECT c.review_id, r.body, c.staff_mentioned, c.evidence_quote,
               c.resolvability, c.resolvability_reason
        FROM classifications c JOIN reviews r USING(review_id)
        """
    ).fetchall()

    if not rows:
        sys.exit("Nothing classified yet. Run `uv run classify.py` first.")

    names_checked = names_bad = 0
    quotes_checked = quotes_bad = 0
    missing_reason = missing_quote = 0
    failures = []

    for review_id, body, staff, quote, resolvability, reason in rows:
        haystack = normalise(body)

        for name in json.loads(staff or "[]"):
            names_checked += 1
            if normalise(name) not in haystack:
                names_bad += 1
                failures.append((review_id, f"staff name {name!r} is not in the review", body))

        if quote:
            quotes_checked += 1
            if normalise(quote) not in haystack:
                quotes_bad += 1
                failures.append((review_id, f"quote {quote!r} is not a span of the review", body))

        if resolvability and not reason:
            missing_reason += 1
            failures.append((review_id, "has a resolvability but no reason", body))

        # "cannot_tell" is the one decision that needs no quote, since the point
        # of it is that the review contains nothing to point at.
        if resolvability and resolvability != "cannot_tell" and not quote:
            missing_quote += 1
            failures.append((review_id, "has a decided resolvability but no quote", body))

    print(f"Checked {len(rows)} classified reviews.\n")
    ok = lambda n: "ok  " if n == 0 else "FAIL"
    print(f"  {ok(names_bad)}  staff names found in the review text     "
          f"{names_checked - names_bad}/{names_checked}")
    print(f"  {ok(quotes_bad)}  evidence quotes are literal spans        "
          f"{quotes_checked - quotes_bad}/{quotes_checked}")
    print(f"  {ok(missing_reason)}  rows with a resolvability have a reason  "
          f"{missing_reason} missing")
    print(f"  {ok(missing_quote)}  decided rows carry a quote              "
          f"{missing_quote} missing")

    if failures:
        print(f"\n{len(failures)} rows to look at:\n")
        for review_id, problem, body in failures[:25]:
            print(f"  review {review_id}: {problem}")
            print(textwrap.fill(" ".join(body.split())[:200], 74,
                                initial_indent="    ", subsequent_indent="    "))
            print()
        if len(failures) > 25:
            print(f"  ...and {len(failures) - 25} more")
        sys.exit(1)

    print("\nNothing was invented. Every name and every quote is in its source review.")
    print("This does not mean the judgements are right. It means they are checkable.")


if __name__ == "__main__":
    main()
