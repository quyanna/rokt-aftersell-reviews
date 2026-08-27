# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Stage 3b: check Claude's classifications by hand.

This exists because a classification you have not checked is a guess with good
formatting. It shows you a random sample of reviews WITHOUT the model's answer,
records what you think, and only then compares.

Reads and writes  data/reviews.db  (table: audit)

Usage:
    uv run audit.py            # label the next unlabelled review in the sample
    uv run audit.py --size 50  # draw a fresh sample of this many (default 50)
    uv run audit.py --report   # compare your labels against the model's

The sample is stratified: every complaint type the model found is represented,
so the audit cannot accidentally consist of fifty easy five-star reviews.
"""

import json
import random
import sqlite3
import sys
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "reviews.db"
SAMPLE_SIZE = 50

TABLE = """
CREATE TABLE IF NOT EXISTS audit (
    review_id       INTEGER PRIMARY KEY REFERENCES reviews(review_id),
    my_complaint    TEXT,   -- NULL until labelled
    my_resolvability TEXT,
    note            TEXT
);
"""

RESOLVABILITY = [
    "support_can_fix",
    "explain_only",
    "needs_engineering",
    "cannot_tell_from_the_review",
]

# The rule the classifier follows, written down so you apply the same one. If you
# judge by a different rule, the agreement rate measures the difference between
# the rules rather than how reliable the model is.
RULES = """  NAMED problem  -> pick a complaint type, even in a glowing 5-star review.
                    "doesn't work due to a theme issue" names what broke.
  UNNAMED problem -> no_complaint, even though it clearly generated a ticket.
                    "had some issues but support fixed it" names nothing, so
                    there is no ticket type to record.

  Resolvability, if there is a complaint:
    support_can_fix   an agent with admin access, willing to change settings or
                      write CSS, resolves it in the ticket. Refunds included.
    explain_only      nothing is broken. A Shopify rule, the pricing model
                      working as designed, or a feature that does not exist.
    needs_engineering a real defect. Support can only reproduce and escalate.
    cannot_tell       the review does not contain enough to decide. USE THIS
                      FREELY. It is a finding, not a failure to answer.

  What this dataset does prove, so you are not guessing about it:
    Support DOES write custom CSS and do layout work. 65 reviews describe it.
    Support DOES issue refunds and credits. Merchants describe receiving them.
    Aftersell's pricing and plan terms are public on the App Store listing.
    The 265-page doc index shows whether a feature exists or genuinely does not.

  What nothing here can tell you, so reach for cannot_tell:
    Whether a described bug is a real defect or a misconfiguration. Telling
    those apart needs someone to reproduce it.
    Whether a specific charge was correct. That needs the merchant's invoice
    against their plan, which is not public."""


def draw_sample(db, size):
    """Pick a stratified random sample, spread across what the model found."""
    groups = {}
    for review_id, complaint in db.execute(
        "SELECT review_id, COALESCE(complaint_type, 'no_complaint') FROM classifications"
    ):
        groups.setdefault(complaint, []).append(review_id)

    random.seed(20260826)  # fixed so the sample is the same for anyone re-running
    chosen, per_group = [], max(1, size // len(groups))
    for ids in groups.values():
        random.shuffle(ids)
        chosen.extend(ids[:per_group])

    # Top up to the requested size from whatever is left, largest groups first.
    leftover = [i for ids in groups.values() for i in ids if i not in set(chosen)]
    random.shuffle(leftover)
    chosen.extend(leftover[: max(0, size - len(chosen))])

    db.executemany(
        "INSERT OR IGNORE INTO audit (review_id) VALUES (?)", [(i,) for i in chosen]
    )
    db.commit()
    return len(chosen)


def ask(question, options):
    """Show a numbered menu and return the chosen option."""
    print(f"\n{question}")
    for n, option in enumerate(options, 1):
        print(f"  {n}. {option}")
    while True:
        answer = input("  > ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if answer == "":
            return None
        print("  Type a number, or press enter to skip this review.")


def label_next(db, complaint_types):
    """Show one unlabelled review and record a judgement. Model answer hidden."""
    row = db.execute(
        """
        SELECT r.review_id, r.app, r.rating, r.tenure_raw, r.body
        FROM audit a JOIN reviews r USING(review_id)
        WHERE a.my_complaint IS NULL LIMIT 1
        """
    ).fetchone()

    if row is None:
        print("Every review in the sample is labelled. Run with --report to compare.")
        return False

    review_id, app, rating, tenure, body = row
    left = db.execute("SELECT COUNT(*) FROM audit WHERE my_complaint IS NULL").fetchone()[0]

    print("\n" + "=" * 76)
    print(f"{left} left to label.  {app}, {rating} stars, {tenure or 'tenure not stated'}")
    print("=" * 76)
    print(textwrap.fill(" ".join(body.split()), 74))
    print("\n" + "-" * 76)
    print(RULES)
    print("-" * 76)

    complaint = ask("Primary complaint?", complaint_types + ["no_complaint"])
    if complaint is None:
        print("Skipped.")
        return True

    resolvability = None
    if complaint != "no_complaint":
        resolvability = ask(
            "Who can resolve it?  (pick cannot_tell freely, it is a real answer)",
            RESOLVABILITY,
        )

    note = input("\n  Note (optional, press enter to skip): ").strip() or None
    db.execute(
        "UPDATE audit SET my_complaint=?, my_resolvability=?, note=? WHERE review_id=?",
        (complaint, resolvability, note, review_id),
    )
    db.commit()
    return True


def report(db):
    """Compare hand labels against the model's, and print every disagreement."""
    rows = db.execute(
        """
        SELECT a.review_id, a.my_complaint, a.my_resolvability, a.note,
               c.complaint_type, c.resolvability, c.confidence, r.rating, r.body,
               c.resolvability_reason
        FROM audit a
        JOIN classifications c USING(review_id)
        JOIN reviews r USING(review_id)
        WHERE a.my_complaint IS NOT NULL
        """
    ).fetchall()

    if not rows:
        sys.exit("Nothing labelled yet. Run `uv run audit.py` first.")

    complaint_agree = resolvability_agree = resolvability_total = 0
    undecidable = 0
    disagreements = []

    for rid, mine_c, mine_r, note, model_c, model_r, conf, rating, body, why in rows:
        model_c = model_c or "no_complaint"
        if mine_c == model_c:
            complaint_agree += 1
        if mine_r == "cannot_tell_from_the_review":
            # Not a disagreement. It says the review cannot settle the question,
            # which is the more useful thing to know about that row.
            undecidable += 1
            mine_r = None
        elif mine_r:
            resolvability_total += 1
            if mine_r == model_r:
                resolvability_agree += 1
        if mine_c != model_c or (mine_r and mine_r != model_r):
            disagreements.append(
                (rid, mine_c, model_c, mine_r, model_r, conf, rating, body, note, why)
            )

    n = len(rows)
    print(f"\n{n} reviews labelled by hand and compared.\n")
    print(f"  Complaint type agrees on    {complaint_agree}/{n}"
          f"  ({complaint_agree / n:.0%})")
    if resolvability_total:
        print(f"  Resolvability agrees on     {resolvability_agree}/{resolvability_total}"
              f"  ({resolvability_agree / resolvability_total:.0%})")
    if undecidable:
        judged = undecidable + resolvability_total
        print(f"\n  You could not decide {undecidable} of {judged} resolvability calls"
              f" ({undecidable / judged:.0%}) from the review alone.")
        print("  The model answered all of them anyway. That gap is a finding:")
        print("  it sizes how much of the fix/explain/escalate split is inference")
        print("  rather than knowledge, and it belongs in the report.")

    if not disagreements:
        print("\nNo disagreements.")
        return

    print(f"\n{len(disagreements)} disagreements, listed in full:\n")
    for rid, mine_c, model_c, mine_r, model_r, conf, rating, body, note, why in disagreements:
        print("-" * 76)
        print(f"review {rid}, {rating} stars, model confidence {conf}")
        print(textwrap.fill(" ".join(body.split()), 74)[:400])
        if mine_c != model_c:
            print(f"  complaint:     you said {mine_c}, model said {model_c}")
        if mine_r and mine_r != model_r:
            print(f"  resolvability: you said {mine_r}, model said {model_r}")
            if why:
                print(textwrap.fill(f"  the model's reason: {why}", 74,
                                    subsequent_indent="    "))
        if note:
            print(f"  your note: {note}")


def main():
    db = sqlite3.connect(DB_PATH)
    db.executescript(TABLE)

    if not db.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]:
        sys.exit("Nothing classified yet. Run `uv run classify.py` first.")

    if "--report" in sys.argv:
        report(db)
        return

    size = SAMPLE_SIZE
    if "--size" in sys.argv:
        size = int(sys.argv[sys.argv.index("--size") + 1])

    if not db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]:
        drawn = draw_sample(db, size)
        print(f"Drew a stratified sample of {drawn} reviews.")
        print("You will see each one WITHOUT the model's answer. Label it, then")
        print("run `uv run audit.py --report` to see where you disagreed.")

    # Offer the same category list the model was given, so the comparison is fair.
    complaint_types = sorted(
        {c for (c,) in db.execute(
            "SELECT DISTINCT complaint_type FROM classifications WHERE complaint_type IS NOT NULL"
        )}
    )

    while label_next(db, complaint_types):
        if input("\n  Another? [Y/n] ").strip().lower() in ("n", "q"):
            break


if __name__ == "__main__":
    main()
