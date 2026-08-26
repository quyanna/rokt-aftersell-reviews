# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic"]
# ///
"""
Stage 3 of 5: ask Claude to categorise every review, and save the answers.

Reads   data/reviews.db          (written by parse.py)
Writes  the `classifications` table in the same database

Every answer is cached by review id, so re-running only classifies reviews that
have not been done yet. Interrupting the run is safe: rows are committed as they
arrive, not at the end.

The model's raw response is stored next to every label, so any number in the
final report can be traced back to what the model actually said.

Usage:
    uv run classify.py            # classify everything not yet done
    uv run classify.py --limit 20 # try a small batch first
"""

import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "reviews.db"

# Opus 5 rather than a cheaper model because `resolvability` is a judgement call
# and every finding in stage 5 rests on it. The whole run costs a few dollars.
MODEL = "claude-opus-5"
EFFORT = "medium"
WORKERS = 8

COMPLAINT_TYPES = [
    "billing_surprise",
    "cancellation_or_uninstall_trouble",
    "app_unreliable",
    "offer_not_firing",
    "theme_or_styling_conflict",
    "third_party_integration_broken",
    "shopify_platform_limit",
    "feature_missing",
    "unexpected_order_change",
    "no_measurable_return",
    "support_only",
    "other",
]

PRAISE_TYPES = [
    "support_quality",
    "revenue_result",
    "ease_of_setup",
    "customisation_help",
    "app_quality_general",
    "other",
]

SYSTEM = """You are helping a customer support team triage merchant feedback for \
two Shopify apps built by Rokt: Aftersell (post-purchase upsells shown after \
checkout) and UpCart (a cart drawer).

You will be given one public App Store review. Classify it. The audience is a \
support agent deciding what to do about tickets like this one, so accuracy about \
who can resolve the problem matters more than anything else.

Reviews may be in any language. Classify them the same way regardless, and write \
your summary in English.

FIELDS

sentiment: "negative", "mixed" or "positive". Judge the text, not the star rating; \
they sometimes disagree.

complaint_type: the merchant's PRIMARY problem, or null if the review contains no \
complaint. Choose exactly one:
- billing_surprise: charged unexpectedly, usage fees not understood, price rose \
  without warning, charged after uninstalling, asking for a refund.
- cancellation_or_uninstall_trouble: cannot find how to cancel or turn something \
  off, a feature is stuck behind a paywall, uninstalling damaged the store.
- app_unreliable: crashes, freezes, blank screens, work lost, bugs that come back.
- offer_not_firing: the upsell or funnel does not trigger when it should.
- theme_or_styling_conflict: breaks with a specific theme, layout or styling wrong, \
  conflicts with another app's display.
- third_party_integration_broken: breaks an outside tool, such as Klaviyo \
  add-to-cart tracking, analytics double counting, or ad platform attribution.
- shopify_platform_limit: Shopify itself forbids what the merchant wants. The \
  clearest case is post-purchase upsells not working with Apple Pay, Shop Pay or \
  Google Pay. Use this ONLY for genuine Shopify platform constraints.
- feature_missing: the app genuinely lacks a capability, such as translations, \
  multi-currency or A/B testing. This is the app's roadmap, NOT a Shopify limit. \
  Merchants confuse the two; you should not.
- unexpected_order_change: products added to a customer's order without consent, \
  duplicate charges, chargebacks caused by the app.
- no_measurable_return: the app works but the merchant sees no revenue from it.
- support_only: support quality IS the whole complaint. Use this when the merchant \
  is unhappy about slow, absent or unhelpful support and names no underlying \
  technical or billing problem. If they do name one, use that category instead and \
  record the support problem in support_failure.
- other: a real complaint that fits nothing above.

secondary_complaint: a second complaint_type value if the review clearly raises \
another distinct problem, otherwise null. Never repeat complaint_type.

support_failure: true if the review complains about support quality, speed, \
availability or unhelpfulness. This is separate from complaint_type on purpose, \
because it usually accompanies some other problem. Set it independently.

resolvability: who can resolve this, or null if there is no complaint.
- "support_can_fix": a support agent with normal admin access, able to change \
  settings and write CSS or HTML, could resolve this within the ticket. Includes \
  refunds and credits, configuration changes, theme styling fixes, and showing a \
  merchant where a setting lives.
- "explain_only": nothing is broken. The constraint is real, whether it is a \
  Shopify platform rule, the pricing model working as designed, or a feature that \
  genuinely does not exist. Support explains it and sets expectations.
- "needs_engineering": a genuine defect in the app. Support can reproduce it and \
  gather evidence, but only engineering can fix it.

praise_type: what the merchant is happy about, or null if the review is not \
positive. Choose exactly one:
- support_quality: support was fast, helpful, or went beyond what was asked.
- revenue_result: the app made them money, raised average order value, or converted.
- ease_of_setup: quick or simple to install and configure.
- customisation_help: the team built or coded something specific for them.
- app_quality_general: general praise with no specific reason given.
- other

staff_mentioned: an array of first names of Rokt, Aftersell or UpCart staff the \
review names as having helped or failed to help. Names only, as written. Do NOT \
include the merchant's own name, their store name, the reviewer, or product names. \
Empty array if nobody is named.

wanted: one plain sentence saying what the merchant actually wanted to happen. \
Write it as the underlying request, not a paraphrase of their tone. For a review \
with no complaint, say what they valued.

confidence: "high", "medium" or "low". Use low when the review is too short or \
vague to classify with any confidence, which is common.

resolvability must NOT be null whenever complaint_type is not null. Every complaint \
has someone who owns it. A complaint purely about support quality is \
"support_can_fix", because responding faster and more helpfully is within support's \
control.

Be strict about resolvability. When a merchant is angry about something that is \
genuinely Shopify's constraint or genuinely the documented pricing model, that is \
"explain_only" even though they are furious. When an app repeatedly breaks, that \
is "needs_engineering" even if support was polite about it."""

def nullable_enum(values):
    """A field that is either one of `values` or null.

    JSON Schema will not accept `enum` alongside a type union like
    ["string", "null"], so the two cases are spelled out as separate branches.
    """
    return {"anyOf": [{"type": "string", "enum": values}, {"type": "null"}]}


SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["negative", "mixed", "positive"]},
        "complaint_type": nullable_enum(COMPLAINT_TYPES),
        "secondary_complaint": nullable_enum(COMPLAINT_TYPES),
        "support_failure": {"type": "boolean"},
        "resolvability": nullable_enum(
            ["support_can_fix", "explain_only", "needs_engineering"]
        ),
        "praise_type": nullable_enum(PRAISE_TYPES),
        "staff_mentioned": {"type": "array", "items": {"type": "string"}},
        "wanted": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "sentiment", "complaint_type", "secondary_complaint", "support_failure",
        "resolvability", "praise_type", "staff_mentioned", "wanted", "confidence",
    ],
    "additionalProperties": False,
}

TABLE = """
CREATE TABLE IF NOT EXISTS classifications (
    review_id           INTEGER PRIMARY KEY REFERENCES reviews(review_id),
    sentiment           TEXT,
    complaint_type      TEXT,
    secondary_complaint TEXT,
    support_failure     INTEGER,
    resolvability       TEXT,
    praise_type         TEXT,
    staff_mentioned     TEXT,   -- JSON array
    wanted              TEXT,
    confidence          TEXT,
    model               TEXT,   -- which model produced this row
    raw_response        TEXT    -- exactly what the model returned, for auditing
);

CREATE TABLE IF NOT EXISTS classification_failures (
    review_id INTEGER PRIMARY KEY,
    error     TEXT
);
"""


def load_env():
    """Read KEY=VALUE lines from .env into the environment, if the file exists."""
    env_file = HERE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Only fill gaps, so a real environment variable always wins over the file.
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def classify_one(client, review):
    """Send one review to Claude. Returns (parsed dict, raw text, usage)."""
    review_id, app, rating, tenure, body = review

    product = "Aftersell (post-purchase upsells)" if app == "aftersell" else "UpCart (cart drawer)"
    prompt = (
        f"App: {product}\n"
        f"Star rating: {rating} out of 5\n"
        f"Merchant had used the app for: {tenure or 'not stated'}\n"
        f"Review text:\n{body}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    )

    if response.stop_reason == "refusal":
        raise ValueError(f"model refused: {response.stop_details}")

    raw = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(raw), raw, response.usage


def main():
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Put it in .env or export it.")

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.executescript(TABLE)

    # Reviews with no text have nothing to classify, so they are skipped entirely
    # rather than sent to the model to produce a meaningless answer.
    todo = db.execute(
        """
        SELECT review_id, app, rating, tenure_raw, body FROM reviews
        WHERE TRIM(body) != ''
          AND review_id NOT IN (SELECT review_id FROM classifications)
        ORDER BY rating, review_id
        """
    ).fetchall()

    already = db.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
    if limit:
        todo = todo[:limit]

    print(f"{already} already classified, {len(todo)} to do, model {MODEL}")
    if not todo:
        summarise(db)
        return

    client = anthropic.Anthropic()
    lock = threading.Lock()
    done = {"n": 0, "failed": 0, "in_tok": 0, "cached_tok": 0, "out_tok": 0}

    def work(review):
        review_id = review[0]
        try:
            parsed, raw, usage = classify_one(client, review)
        except Exception as problem:
            # One bad review must never end a run of 1,500. Record it and move on.
            with lock:
                db.execute(
                    "INSERT OR REPLACE INTO classification_failures VALUES (?,?)",
                    (review_id, f"{type(problem).__name__}: {problem}"),
                )
                db.commit()
                done["failed"] += 1
            return

        with lock:
            db.execute(
                "INSERT OR REPLACE INTO classifications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    review_id,
                    parsed.get("sentiment"),
                    parsed.get("complaint_type"),
                    parsed.get("secondary_complaint"),
                    int(bool(parsed.get("support_failure"))),
                    parsed.get("resolvability"),
                    parsed.get("praise_type"),
                    json.dumps(parsed.get("staff_mentioned") or []),
                    parsed.get("wanted"),
                    parsed.get("confidence"),
                    MODEL,
                    raw,
                ),
            )
            db.commit()
            done["n"] += 1
            done["in_tok"] += usage.input_tokens
            done["cached_tok"] += getattr(usage, "cache_read_input_tokens", 0) or 0
            done["out_tok"] += usage.output_tokens
            if done["n"] % 25 == 0 or done["n"] + done["failed"] == len(todo):
                print(f"  {done['n']}/{len(todo)} done, {done['failed']} failed")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, todo))

    # Opus 5 list pricing, for a rough sense of spend rather than a billing figure.
    cost = (done["in_tok"] * 5 + done["cached_tok"] * 0.5 + done["out_tok"] * 25) / 1e6
    print(f"\n{done['n']} classified, {done['failed']} failed")
    print(f"tokens: {done['in_tok']:,} in ({done['cached_tok']:,} cached), "
          f"{done['out_tok']:,} out, roughly ${cost:.2f}")
    summarise(db)


def summarise(db):
    ask = lambda sql: db.execute(sql).fetchall()

    total = ask("SELECT COUNT(*) FROM classifications")[0][0]
    if not total:
        return
    print(f"\n{total} reviews classified")

    print("\nWho could resolve it (reviews with a complaint)")
    for label, count in ask(
        "SELECT resolvability, COUNT(*) FROM classifications"
        " WHERE resolvability IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {label:<22}{count:>6}")

    print("\nComplaint types")
    for label, count in ask(
        "SELECT complaint_type, COUNT(*) FROM classifications"
        " WHERE complaint_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {label:<36}{count:>6}")

    flagged = ask("SELECT COUNT(*) FROM classifications WHERE support_failure = 1")[0][0]
    print(f"\n{flagged} reviews mention a support failure")

    print("\nWhat the praise is about")
    for label, count in ask(
        "SELECT praise_type, COUNT(*) FROM classifications"
        " WHERE praise_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {label:<26}{count:>6}")

    print("\nMost mentioned support staff")
    names = {}
    for (blob,) in ask("SELECT staff_mentioned FROM classifications"):
        for name in json.loads(blob or "[]"):
            names[name.strip()] = names.get(name.strip(), 0) + 1
    for name, count in sorted(names.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {name:<20}{count:>5}  {'#' * count}")

    failures = ask("SELECT COUNT(*) FROM classification_failures")[0][0]
    if failures:
        print(f"\n{failures} reviews failed to classify. Re-run to retry them.")


if __name__ == "__main__":
    main()
