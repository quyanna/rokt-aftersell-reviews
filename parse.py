# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""
Stage 2 of 5: read the saved HTML pages and put one row per review into SQLite.

Reads   data/raw/<app>/page-NNN.html   (written by fetch.py)
Writes  data/reviews.db

Re-running is safe. Each review carries a stable id from the page, so rows are
replaced rather than duplicated, and the database can be rebuilt from scratch at
any time by deleting the file.

Usage:
    uv run parse.py
"""

import glob
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
RAW_DIR = HERE / "data" / "raw"
DB_PATH = HERE / "data" / "reviews.db"

# Tenure is published as text like "Over 1 year using the app". Every one of the
# 1,765 strings in this dataset matches this pattern.
TENURE = re.compile(
    r"^(About|Over|Almost|Less than)?\s*(\d+)?\s*"
    r"(minute|hour|day|week|month|year)s?\s+using the app$"
)

# How many months each unit is worth. These are for rough grouping only, which is
# why a month is a flat 30.44 days rather than anything calendar-aware.
MONTHS_PER = {
    "minute": 1 / (60 * 24 * 30.44),
    "hour": 1 / (24 * 30.44),
    "day": 1 / 30.44,
    "week": 7 / 30.44,
    "month": 1.0,
    "year": 12.0,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id     INTEGER PRIMARY KEY,  -- Shopify's own id, stable across pages
    app           TEXT    NOT NULL,
    rating        INTEGER NOT NULL,     -- 1 to 5
    review_date   TEXT    NOT NULL,     -- YYYY-MM-DD
    is_edited     INTEGER NOT NULL,     -- 1 if the page said "Edited". See below.
    body          TEXT    NOT NULL,
    store_name    TEXT,
    country       TEXT,
    tenure_raw    TEXT,                 -- verbatim, e.g. "Over 1 year using the app"
    tenure_months REAL,                 -- approximate. Qualifier is discarded.
    tenure_bucket TEXT,
    reply_body    TEXT,                 -- developer reply, NULL if none
    reply_date    TEXT,                 -- YYYY-MM-DD
    source_page   INTEGER NOT NULL      -- which saved file this came from
);

-- On is_edited: when a merchant edits a review, the page shows the date of the
-- EDIT, not of the original. The original date is not published anywhere, so for
-- these rows review_date is a later bound, not the date the merchant first wrote.

CREATE INDEX IF NOT EXISTS reviews_app_rating ON reviews (app, rating);
CREATE INDEX IF NOT EXISTS reviews_tenure ON reviews (tenure_bucket);
"""


def parse_date(text):
    """'June 4, 2026' -> '2026-06-04'. Returns None if it does not look like a date."""
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_tenure(text):
    """'Over 1 year using the app' -> (1 year in months, bucket label)."""
    match = TENURE.match(text.strip())
    if not match:
        return None, None

    _qualifier, count, unit = match.groups()
    # The qualifier is deliberately ignored. "Over 1 year", "About 1 year" and
    # "Almost 1 year" all become 12 months. Turning those words into a multiplier
    # would invent precision the source does not have. tenure_raw keeps the
    # original text so anyone can do better.
    count = int(count) if count else 1
    months = count * MONTHS_PER[unit]

    if unit in ("minute", "hour"):
        bucket = "first day"
    elif unit == "day":
        bucket = "first week" if count <= 7 else "first month"
    elif unit == "week":
        bucket = "first week" if count <= 1 else "first month"
    elif unit == "month":
        bucket = "1-3 months" if count < 3 else "3-6 months" if count < 6 else "6-12 months"
    else:
        bucket = "1-2 years" if count < 2 else "2+ years"

    return round(months, 3), bucket


def parse_review(block, app, page):
    """Turn one review element into a dict ready for the database."""
    review_id = block.get("data-review-content-id")

    # Pull the developer reply out of the tree first. The reply contains its own
    # date and its own body, marked up exactly like the review's, so removing it
    # means the selectors below cannot accidentally pick up the reply's copy.
    reply_body = reply_date = None
    reply = block.select_one("[data-merchant-review-reply]")
    if reply is not None:
        if reply.get_text(strip=True):
            header = reply.select_one(".tw-text-fg-tertiary")
            if header:
                # Reads "Rokt replied<newline>May 19, 2026"
                reply_date = parse_date(header.get_text(" ", strip=True).split("replied")[-1])
            copy = reply.select_one("[data-truncate-content-copy]")
            if copy:
                reply_body = copy.get_text("\n", strip=True)
        reply.decompose()

    stars = block.select_one("[aria-label$='out of 5 stars']")
    rating = int(stars["aria-label"][0])

    date_text = block.select_one(".tw-text-fg-tertiary").get_text(" ", strip=True)
    is_edited = date_text.startswith("Edited")
    review_date = parse_date(date_text.removeprefix("Edited"))

    body_el = block.select_one("[data-truncate-content-copy]")
    body = body_el.get_text("\n", strip=True) if body_el else ""

    # The sidebar holds store name, country and tenure as three plain divs with
    # no distinguishing attributes, so they are identified by content rather than
    # by position. One review in the dataset has no tenure line at all.
    name_el = block.select_one("[title]")
    store_name = name_el["title"].strip() if name_el else None

    sidebar = name_el.find_parent("div").find_parent("div") if name_el else None
    lines = []
    if sidebar:
        for div in sidebar.find_all("div", recursive=False):
            # Skip the div holding the store name, or it gets mistaken for the
            # country: both are plain divs and the store name comes first.
            if name_el in div.descendants or div is name_el.parent:
                continue
            lines.append(div.get_text(" ", strip=True))

    tenure_raw = next((line for line in lines if line.endswith("using the app")), None)
    country = next((line for line in lines if line and line != tenure_raw), None)

    tenure_months, tenure_bucket = parse_tenure(tenure_raw) if tenure_raw else (None, None)

    return {
        "review_id": int(review_id),
        "app": app,
        "rating": rating,
        "review_date": review_date,
        "is_edited": int(is_edited),
        "body": body,
        "store_name": store_name,
        "country": country,
        "tenure_raw": tenure_raw,
        "tenure_months": tenure_months,
        "tenure_bucket": tenure_bucket,
        "reply_body": reply_body,
        "reply_date": reply_date,
        "source_page": page,
    }


def check(db):
    """Assert the parse is sane. Runs on every parse so it cannot rot."""
    ask = lambda sql: db.execute(sql).fetchone()[0]

    assert ask("SELECT COUNT(*) FROM reviews") > 0, "no reviews parsed"
    assert ask("SELECT COUNT(*) FROM reviews WHERE rating NOT BETWEEN 1 AND 5") == 0
    assert ask("SELECT COUNT(*) FROM reviews WHERE review_date IS NULL") == 0
    assert ask("SELECT COUNT(*)-COUNT(DISTINCT review_id) FROM reviews") == 0, "duplicate ids"
    assert ask("SELECT COUNT(*) FROM reviews WHERE country = store_name") == 0, (
        "country column is holding the store name"
    )
    assert ask("SELECT COUNT(*) FROM reviews WHERE country LIKE '%using the app'") == 0, (
        "country column is holding the tenure string"
    )
    assert ask("SELECT COUNT(*) FROM reviews WHERE body LIKE '%Rokt replied%'") == 0, (
        "the developer reply leaked into the review body"
    )
    assert ask("SELECT COUNT(*) FROM reviews WHERE reply_body IS NOT NULL"
               " AND reply_date IS NULL") == 0, "reply without a date"
    assert ask("SELECT COUNT(*) FROM reviews WHERE tenure_raw IS NOT NULL"
               " AND tenure_months IS NULL") == 0, "tenure text that did not parse"

    # A reply can legitimately predate its review, but only when the merchant
    # edited the review afterwards. Any other case means the dates are crossed.
    assert ask("SELECT COUNT(*) FROM reviews WHERE reply_date < review_date"
               " AND is_edited = 0") == 0, "reply predates an unedited review"

    print("  checks passed")


def summarise(db):
    """Print what ended up in the database."""
    ask = lambda sql: db.execute(sql).fetchall()

    print("\nReviews by app and rating")
    print(f"  {'app':<24}{'1':>6}{'2':>6}{'3':>6}{'4':>6}{'5':>6}{'total':>8}")
    for app, in ask("SELECT DISTINCT app FROM reviews ORDER BY app"):
        counts = dict(
            ask(f"SELECT rating, COUNT(*) FROM reviews WHERE app='{app}' GROUP BY rating")
        )
        row = "".join(f"{counts.get(n, 0):>6}" for n in range(1, 6))
        print(f"  {app:<24}{row}{sum(counts.values()):>8}")

    total, replies, edited, undated = ask(
        "SELECT COUNT(*), SUM(reply_body IS NOT NULL), SUM(is_edited),"
        " SUM(review_date IS NULL) FROM reviews"
    )[0]
    first, last = ask("SELECT MIN(review_date), MAX(review_date) FROM reviews")[0]

    print(f"\n  {total} reviews, {first} to {last}")
    print(f"  {replies} have a developer reply ({replies / total:.0%})")
    print(f"  {edited} were edited, so their date is the edit date, not the original")
    if undated:
        print(f"  {undated} could not have their date parsed")

    print("\nHow long the merchant had used the app")
    for bucket, count in ask(
        "SELECT COALESCE(tenure_bucket, 'not stated'), COUNT(*) FROM reviews"
        " GROUP BY 1 ORDER BY MIN(COALESCE(tenure_months, 1e9))"
    ):
        print(f"  {bucket:<16}{count:>6}  {'#' * round(count / 12)}")

    print("\nNegative reviews (1-3 stars) by app")
    for app, count in ask(
        "SELECT app, COUNT(*) FROM reviews WHERE rating <= 3 GROUP BY app ORDER BY app"
    ):
        print(f"  {app:<24}{count:>6}")


def main():
    files = sorted(glob.glob(str(RAW_DIR / "*" / "page-*.html")))
    if not files:
        sys.exit(f"No saved pages under {RAW_DIR}. Run `uv run fetch.py` first.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)

    columns = None
    parsed = 0

    for path in files:
        path = Path(path)
        app = path.parent.name
        page = int(path.stem.split("-")[1])
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

        for block in soup.select("[data-merchant-review]"):
            row = parse_review(block, app, page)
            columns = columns or list(row)
            db.execute(
                f"INSERT OR REPLACE INTO reviews ({','.join(columns)})"
                f" VALUES ({','.join('?' * len(columns))})",
                [row[c] for c in columns],
            )
            parsed += 1

    db.commit()
    print(f"Parsed {parsed} reviews from {len(files)} pages into {DB_PATH}")
    check(db)
    summarise(db)
    db.close()


if __name__ == "__main__":
    main()
