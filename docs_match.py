# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic"]
# ///
"""
Stage 4 of 5: check each complaint type against Aftersell's own documentation.

Reads   data/reviews.db, and data/docs/llms.txt (downloaded on first run)
Writes  the `doc_coverage` table in the database

The question is not "do the docs mention this". It is "would the merchant who
wrote this review have found the page". A detailed article explaining exactly
why Apple Pay cannot trigger post-purchase upsells does the merchant no good if
it is titled something they would never search for. That distinction is the
whole point of this stage, so it is what the three tags measure:

    documented_easy_to_find  a page covers it AND uses the words merchants use
    documented_but_buried    a page covers it, but not in the merchant's words
    not_documented           nothing covers it

Usage:
    uv run docs_match.py
    uv run docs_match.py --refresh   # re-download the index and redo the matching
"""

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "reviews.db"
INDEX_PATH = HERE / "data" / "docs" / "llms.txt"
INDEX_URL = "https://docs.aftersell.com/llms.txt"
USER_AGENT = (
    "aftersell-review-triage/1.0 "
    "(portfolio project; contact quyannacampbell@gmail.com)"
)
MODEL = "claude-opus-5"

SYSTEM = """You are auditing whether a company's help documentation covers the \
problems its customers actually complain about.

You will be given the complete index of Aftersell's public documentation (265 \
pages, each with a title and a description), one complaint category, and real \
quotes from merchants who had that complaint.

Decide which of three tags applies, and be strict about the distinction:

"documented_easy_to_find" - one or more pages clearly cover this problem, AND \
their titles use words a merchant with this complaint would actually search for. \
Test it against the quotes: if a merchant typed the words in those quotes into a \
search box, would these titles come back?

"documented_but_buried" - a page covers the problem, but its title or framing uses \
internal or product vocabulary rather than the merchant's. The writing is not the \
failure here; findability is. This is the most useful tag when it is true, because \
the fix is renaming or cross-linking a page rather than writing a new one.

"not_documented" - no page covers this problem.

Judge the documentation only from the titles and descriptions you are given. Do \
not assume a page contains more than its description claims, and do not invent \
pages that are not in the index.

Return:
- tag: one of the three above
- pages: array of the most relevant page URLs from the index, best first, at most \
  three. Empty array if not_documented. Copy URLs exactly; never invent one.
- reason: one or two plain sentences explaining the tag. If buried, say what \
  vocabulary gap causes it. If not documented, say what page would need writing.
- suggested_title: only when the tag is documented_but_buried, a better title using \
  merchant vocabulary. Otherwise null."""

SCHEMA = {
    "type": "object",
    "properties": {
        "tag": {
            "type": "string",
            "enum": ["documented_easy_to_find", "documented_but_buried", "not_documented"],
        },
        "pages": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
        "suggested_title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["tag", "pages", "reason", "suggested_title"],
    "additionalProperties": False,
}

TABLE = """
CREATE TABLE IF NOT EXISTS doc_coverage (
    complaint_type  TEXT PRIMARY KEY,
    tag             TEXT,
    pages           TEXT,   -- JSON array of URLs
    reason          TEXT,
    suggested_title TEXT,
    raw_response    TEXT
);
"""


def load_env():
    """Read KEY=VALUE lines from .env into the environment, if the file exists."""
    env_file = HERE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip().removeprefix("export ").strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def doc_index(refresh=False):
    """Return the doc index, downloading it once and reusing it afterwards."""
    if INDEX_PATH.exists() and not refresh:
        return INDEX_PATH.read_text(encoding="utf-8")

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")

    if "docs.aftersell.com" not in text:
        raise RuntimeError(f"{INDEX_URL} did not return the expected doc index")
    INDEX_PATH.write_text(text, encoding="utf-8")
    print(f"Downloaded the doc index, {text.count(chr(10)) + 1} lines")
    return text


def main():
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Put it in .env or export it.")

    refresh = "--refresh" in sys.argv
    index = doc_index(refresh)

    db = sqlite3.connect(DB_PATH)
    db.executescript(TABLE)
    if refresh:
        db.execute("DELETE FROM doc_coverage")
        db.commit()

    complaints = [
        row[0] for row in db.execute(
            """
            SELECT complaint_type FROM classifications
            WHERE complaint_type IS NOT NULL
              AND complaint_type NOT IN (SELECT complaint_type FROM doc_coverage)
            GROUP BY complaint_type ORDER BY COUNT(*) DESC
            """
        )
    ]

    if not complaints:
        print("Every complaint type is already checked. Use --refresh to redo it.")
        return report(db)

    client = anthropic.Anthropic()

    for complaint in complaints:
        # Give the model the merchants' own words, since the whole judgement is
        # about whether the doc titles match the vocabulary merchants use.
        quotes = db.execute(
            """
            SELECT r.body, c.wanted FROM classifications c JOIN reviews r USING(review_id)
            WHERE c.complaint_type = ? ORDER BY LENGTH(r.body) DESC LIMIT 8
            """,
            (complaint,),
        ).fetchall()

        quoted = "\n\n".join(
            f'Merchant wrote: "{" ".join(body.split())[:600]}"\nWhat they wanted: {wanted}'
            for body, wanted in quotes
        )

        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM},
                    {"type": "text", "text": f"DOCUMENTATION INDEX\n\n{index}",
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                       f"Complaint category: {complaint}\n\n"
                       f"Real merchant complaints in this category:\n\n{quoted}"}],
            output_config={"effort": "high",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
        )

        raw = next((b.text for b in response.content if b.type == "text"), "")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as problem:
            print(f"  {complaint}: could not parse the response ({problem}), skipping")
            continue

        db.execute(
            "INSERT OR REPLACE INTO doc_coverage VALUES (?,?,?,?,?,?)",
            (complaint, result["tag"], json.dumps(result["pages"]),
             result["reason"], result.get("suggested_title"), raw),
        )
        db.commit()
        print(f"  {complaint:<36}{result['tag']}")

    report(db)


def report(db):
    print("\nDocumentation coverage by complaint type\n")
    for complaint, tag, pages, reason, suggested in db.execute(
        """
        SELECT d.complaint_type, d.tag, d.pages, d.reason, d.suggested_title
        FROM doc_coverage d
        LEFT JOIN (SELECT complaint_type, COUNT(*) n FROM classifications GROUP BY 1) c
          ON c.complaint_type = d.complaint_type
        ORDER BY c.n DESC
        """
    ):
        count = db.execute(
            "SELECT COUNT(*) FROM classifications WHERE complaint_type = ?", (complaint,)
        ).fetchone()[0]
        print(f"{complaint}  ({count} reviews)")
        print(f"  {tag}")
        print(f"  {reason}")
        for url in json.loads(pages or "[]"):
            print(f"    {url}")
        if suggested:
            print(f"  suggested title: {suggested}")
        print()


if __name__ == "__main__":
    main()
