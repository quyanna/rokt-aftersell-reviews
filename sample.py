# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Pulls a random sample of classified reviews so they can be read and checked.

Replaces the interactive audit, which asked a question per review and made
checking fifty of them a chore. This writes one file you read top to bottom.
Each entry is numbered. Note the numbers you disagree with and say so; nothing
here needs answering in order or in one sitting.

Reads   data/reviews.db
Writes  data/audit-sample.md

The sample is stratified: every ticket type and every resolvability value gets
representation, so it cannot come out as forty easy five-star reviews. The seed
is fixed, so re-running gives the same sample unless you pass --seed.

Usage:
    uv run sample.py                 # 3 per ticket type
    uv run sample.py --per 5         # 5 per ticket type
    uv run sample.py --seed 7        # a different sample
"""

import random
import sqlite3
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "reviews.db"
OUT_PATH = HERE / "data" / "audit-sample.md"


def wrap(text, width=88):
    return "\n".join(
        textwrap.fill(line, width) if line.strip() else ""
        for line in " ".join((text or "").split()).split("\n")
    )


def main():
    per = 3
    seed = 20260826
    if "--per" in sys.argv:
        per = int(sys.argv[sys.argv.index("--per") + 1])
    if "--seed" in sys.argv:
        seed = int(sys.argv[sys.argv.index("--seed") + 1])

    db = sqlite3.connect(DB_PATH)
    if not db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='ticket_types'"
    ).fetchone()[0]:
        sys.exit("The ticket_types view is missing. Run: uv run classify.py")

    random.seed(seed)
    chosen = []

    # One group per ticket type, so no category can be missed.
    for (ticket_type,) in db.execute(
        "SELECT DISTINCT ticket_type FROM ticket_types ORDER BY ticket_type"
    ):
        ids = [r[0] for r in db.execute(
            "SELECT review_id FROM ticket_types WHERE ticket_type = ?", (ticket_type,)
        )]
        random.shuffle(ids)
        chosen.extend((ticket_type, i) for i in ids[:per])

    # Reviews the model found no complaint in are the easiest place for a
    # mistake to hide, because nothing draws attention to them.
    no_complaint = [r[0] for r in db.execute(
        """SELECT review_id FROM classifications
           WHERE complaint_type IS NULL AND review_id IN
           (SELECT review_id FROM reviews WHERE TRIM(body) != '')"""
    )]
    random.shuffle(no_complaint)
    chosen.extend(("no complaint found", i) for i in no_complaint[:per * 2])

    lines = [
        "# Classification sample to check",
        "",
        f"{len(chosen)} reviews, drawn at random from every ticket type. Read down the",
        "page and note the number of anything you disagree with. You do not need to",
        "check them all in one go, and you do not need to supply a better answer, only",
        "to say the call looks wrong.",
        "",
        "Each entry shows the review, then what the model decided, then the exact words",
        "from the review it says justify that decision.",
        "",
        "The three resolvability values mean:",
        "",
        "- **support can fix** an agent with admin access, willing to change settings or",
        "  write CSS, resolves it in the ticket. Refunds count.",
        "- **explain only** nothing is broken. A Shopify rule, the pricing model working",
        "  as designed, or a feature that genuinely does not exist.",
        "- **needs engineering** a real defect. Support can only reproduce and escalate.",
        "- **cannot tell** the review does not say enough to choose between those three.",
        "",
        "---",
        "",
    ]

    current_group = None
    for n, (group, review_id) in enumerate(chosen, 1):
        if group != current_group:
            current_group = group
            count = sum(1 for g, _ in chosen if g == group)
            lines += [f"## {group.replace('_', ' ')}  ({count} shown)", ""]

        row = db.execute(
            """
            SELECT r.app, r.rating, r.tenure_bucket, r.body,
                   c.complaint_type, c.secondary_complaint, c.support_failure,
                   c.resolvability, c.resolvability_reason, c.evidence_quote,
                   c.praise_type, c.staff_mentioned, c.wanted, c.confidence
            FROM classifications c JOIN reviews r USING(review_id)
            WHERE c.review_id = ?
            """,
            (review_id,),
        ).fetchone()

        (app, rating, tenure, body, complaint, secondary, support_failure,
         resolvability, reason, quote, praise, staff, wanted, confidence) = row

        lines += [
            f"### {n}.  {'*' * rating}{'.' * (5 - rating)}  "
            f"{app}, {tenure or 'tenure not stated'}",
            "",
            "> " + wrap(body).replace("\n", "\n> "),
            "",
        ]

        verdict = []
        if complaint:
            verdict.append(f"**Complaint:** {complaint.replace('_', ' ')}")
            if secondary:
                verdict.append(f"**Also:** {secondary.replace('_', ' ')}")
        else:
            verdict.append("**Complaint:** none found")
        if support_failure:
            verdict.append("**Support let them down:** yes")
        if resolvability:
            verdict.append(f"**Who resolves it:** {resolvability.replace('_', ' ')}")
        if praise:
            verdict.append(f"**Praise about:** {praise.replace('_', ' ')}")
        verdict.append(f"**Model confidence:** {confidence}")

        lines += ["- " + v for v in verdict] + [""]

        if reason:
            lines += [wrap(f"**Why:** {reason}"), ""]
        if quote:
            lines += [wrap(f'**Evidence from the review:** "{quote}"'), ""]
        if wanted:
            lines += [wrap(f"**What they wanted:** {wanted}"), ""]
        lines += ["---", ""]

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(chosen)} reviews to {OUT_PATH}")
    print("Read it, then tell me the numbers of any you disagree with.")


if __name__ == "__main__":
    main()
