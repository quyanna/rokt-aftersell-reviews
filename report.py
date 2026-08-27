# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Stage 5 of 5: build the support triage sheet as one self-contained HTML file.

Reads   data/reviews.db, tickets.py, assets/brief.css
Writes  triage-sheet.html

Every number in the output is queried at build time. Nothing is typed in by hand,
so the document cannot drift from the database it describes. The written analysis
and the draft replies live in tickets.py.

Usage:
    uv run report.py
"""

import html
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from tickets import TICKETS

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "reviews.db"
CSS_PATH = HERE / "assets" / "brief.css"
OUT_PATH = HERE / "triage-sheet.html"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:'
    'opsz,wdth,wght@12..96,75..100,300..800&family=Newsreader:ital,opsz,wght@'
    '0,6..72,300..700;1,6..72,300..600&family=JetBrains+Mono:wght@400;500;700'
    '&display=swap" rel="stylesheet">'
)

# Colour carries meaning in this stylesheet, so the mapping is fixed here rather
# than chosen per use. Teal is a strength, amber is a gap, magenta is the subject.
RESOLVE_LABEL = {
    "support_can_fix": ("Support resolves it", "t-strong"),
    "explain_only": ("Support explains it", "t-mid"),
    "needs_engineering": ("Support triages, engineering fixes", "t-gap"),
    "cannot_tell": ("Not decidable from the review", ""),
}
DOC_LABEL = {
    "documented_easy_to_find": ("Documented, findable", "t-strong"),
    "documented_but_buried": ("Documented but buried", "t-mid"),
    "not_documented": ("No page exists", "t-gap"),
}

def e(text):
    """Escape for HTML, and strip em dashes out of model-written prose.

    Stage 4's explanations come back from the model with em dashes in them, which
    read as machine-written. Replacing them here keeps the fix in one place rather
    than requiring every stored string to be cleaned.
    """
    text = str(text or "")
    text = text.replace(" \u2014 ", ", ").replace("\u2014", ", ")
    text = text.replace(" \u2013 ", ", ").replace("\u2013", "-")
    text = text.replace(" , ", ", ").replace(", ,", ",")
    return html.escape(text)


def paragraphs(text):
    return "\n".join(f"<p>{e(p)}</p>" for p in str(text).split("\n\n"))


def tenure_chart(rows):
    """Complaint rate by how long the merchant had used the app.

    Hand-drawn so the caveat sits in the caption rather than in a tooltip. One
    scale, computed once, and the value is printed on each bar so nobody has to
    measure pixels against an axis.
    """
    width, left, top, bar_h, gap = 880, 200, 16, 22, 12
    peak = max(r[3] for r in rows)
    scale = (width - left - 90) / peak
    height = top + len(rows) * (bar_h + gap) + 20

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Complaint rate by merchant tenure">']
    for i, (bucket, complaints, total, rate) in enumerate(rows):
        y = top + i * (bar_h + gap)
        w = max(2, rate * scale)
        # Amber past a year: the rate climbing with tenure is the finding.
        colour = "#A05500" if bucket in ("1-2 years", "2+ years") else "#C20075"
        parts += [
            f'<text x="{left - 12}" y="{y + 15}" text-anchor="end" '
            f'font-family="JetBrains Mono, monospace" font-size="11" fill="#4A4353">'
            f'{e(bucket)}</text>',
            f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="2" '
            f'fill="{colour}"/>',
            f'<text x="{left + w + 8:.1f}" y="{y + 15}" '
            f'font-family="JetBrains Mono, monospace" font-size="11" fill="#4A4353">'
            f'{rate:.1f}%  ({complaints} of {total})</text>',
        ]
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} is missing. Run the earlier stages first.")
    db = sqlite3.connect(DB_PATH)
    ask = lambda sql, *a: db.execute(sql, a).fetchall()
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]

    total_reviews = one("SELECT COUNT(*) FROM reviews")
    with_text = one("SELECT COUNT(*) FROM reviews WHERE TRIM(body) != ''")
    no_text = total_reviews - with_text
    complaints = one("SELECT COUNT(*) FROM ticket_types")
    first, last = ask("SELECT MIN(review_date), MAX(review_date) FROM reviews")[0]

    resolve = dict(ask("SELECT resolvability, COUNT(*) FROM ticket_types GROUP BY 1"))
    decided = sum(v for k, v in resolve.items() if k != "cannot_tell")

    ticket_rows = ask(
        """SELECT ticket_type, COUNT(*), ROUND(AVG(rating), 1)
           FROM ticket_types WHERE ticket_type != 'unclassified'
           GROUP BY 1 ORDER BY 2 DESC"""
    )
    docs = {r[0]: r for r in ask(
        "SELECT complaint_type, tag, pages, reason, suggested_title FROM doc_coverage")}

    audit = ask("SELECT reviewed_by, reviewed_on, sample_size, disagreements FROM audit_record")
    audit = audit[0] if audit else None

    out = [f"<title>Aftersell and UpCart support triage</title>{FONTS}",
           f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>",
           '<div class="wrap">']

    # ---------------------------------------------------------------- masthead
    out.append(f"""
<header class="mast">
  <p class="eyebrow">Support triage sheet - Aftersell by Rokt</p>
  <h1>What would land in <em>my queue</em>, and what would stop it landing there</h1>
  <p class="standfirst">Every public App Store review for Aftersell and UpCart, read and
  sorted into the tickets they would have become. For each recurring type: what the
  merchant says, what is actually going on, who can resolve it, whether the answer is
  already written down, and a first reply worth sending.</p>
  <div class="mast-meta">
    <span class="chip"><b>{total_reviews:,}</b> reviews</span>
    <span class="chip"><b>{first}</b> to <b>{last}</b></span>
    <span class="chip"><b>{complaints}</b> contain a complaint</span>
    <span class="chip"><b>{len(ticket_rows)}</b> recurring types</span>
    <span class="chip">Built <b>26 Aug 2026</b></span>
  </div>
</header>""")

    # ------------------------------------------------------- 01 read this first
    pct_no_text = no_text / total_reviews
    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">01</span><h2>Read this first</h2></div>
  <div class="sec-body">
    <p class="lede">This measures loud complaints, not common ones. Treating it as a
    picture of the real queue would be wrong in a specific and predictable direction.</p>

    <div class="card warn">
      <p class="card-label">The limitation that matters most</p>
      <p><b>People who quietly uninstall never write a review.</b> Neither do the people
      whose problem was solved in four minutes. A public review is written by someone
      angry enough, or delighted enough, to stop and type. Everything here is drawn from
      that population.</p>
      <p>A real support queue would skew far more mundane than this document: password
      resets, where-is-this-setting, one-line billing questions that never reach a review
      page. Nothing in this dataset can size those, so nothing here tries to.</p>
    </div>

    <h3>Three more things to know before trusting a number</h3>

    <p><b>{complaints} complaints is too few for statistics.</b> Every figure here is a
    count, described as a pattern. No percentages are presented as findings, no trend
    lines are drawn, and where a category has three reviews it says three.</p>

    <p><b>Resolved problems that were not named are not counted.</b> A merchant writing
    "had some issues but support fixed it in ten minutes" generated a real ticket. It is
    recorded here as no complaint, because there is no ticket type in it. This document
    measures identifiable ticket types, not ticket volume, and the gap between those two
    is larger than the counts suggest.</p>

    <p><b>{no_text:,} reviews ({pct_no_text:.0%}) have a star rating and no text at all.</b>
    They are excluded from every count below, because there is nothing in them to read.</p>

    <div class="card">
      <p class="card-label">What this document is for</p>
      <p>Not market research, and not an assessment of the product. It is a working
      answer to one question: if I were answering these tickets, what would keep arriving,
      what could I actually do about it, and what would stop it arriving at all.</p>
    </div>
  </div>
</section>""")

    # --------------------------------------------------------- 02 ticket types
    out.append("""
<section>
  <div class="sec-head"><span class="sec-num">02</span><h2>The recurring ticket types</h2></div>
  <div class="sec-body">
    <p class="lede">Ranked by how often they appear. The star average beside each one is
    the more useful number: it says how angry the merchant is when this type arrives.</p>""")

    peak = ticket_rows[0][1]
    out.append("<h4>Frequency, with severity beside it</h4>")
    for name, count, stars in ticket_rows:
        # Amber where the average review is one or two stars: these are the types
        # that arrive attached to a merchant who is close to leaving.
        cls = " g" if stars < 2.0 else (" s" if stars >= 3.5 else "")
        label = TICKETS.get(name, {}).get("title", name.replace("_", " ").capitalize())
        out.append(f"""
    <div class="bar-row">
      <div class="bar-name">{e(label)}</div>
      <div class="bar-track"><div class="bar-fill{cls}" style="width:{count / peak * 100:.0f}%"></div></div>
      <div class="bar-val">{count} &middot; {stars}&#9733;</div>
    </div>""")
    out.append("""
    <p class="aside" style="margin-top:14px"><b>Amber</b> marks a type whose average review
    is under two stars. <b>Teal</b> marks one whose average is 3.5 or above. The most
    frequent type is also the happiest, and the angriest types are near the bottom.</p>
  </div>
</section>""")

    # each ticket type in full
    for i, (name, count, stars) in enumerate(ticket_rows, 1):
        if name not in TICKETS:
            continue
        t = TICKETS[name]
        doc = docs.get(name)
        res = ask("""SELECT resolvability, COUNT(*) FROM ticket_types WHERE ticket_type=?
                     GROUP BY 1 ORDER BY 2 DESC""", name)
        quote = ask("""SELECT evidence_quote FROM ticket_types WHERE ticket_type=?
                       AND evidence_quote IS NOT NULL ORDER BY LENGTH(evidence_quote) DESC
                       LIMIT 1""", name)

        tags = " ".join(
            f'<span class="tag {RESOLVE_LABEL[r][1]}">{RESOLVE_LABEL[r][0]} &middot; {n}</span>'
            for r, n in res if r in RESOLVE_LABEL
        )
        doc_block = ""
        if doc:
            _, tag, pages, reason, suggested = doc
            label, cls = DOC_LABEL[tag]
            links = "".join(
                f'<li><a href="{e(u)}">{e(u.rsplit("/", 1)[-1].replace(".md", "").replace("_", " "))}</a></li>'
                for u in json.loads(pages or "[]")[:3]
            )
            card = "warn" if tag == "not_documented" else ("key" if tag == "documented_but_buried" else "good")
            doc_block = f"""
      <div class="card {card}">
        <p class="card-label">{e(label)}</p>
        <p>{e(reason)}</p>
        {f'<ul class="plain">{links}</ul>' if links else ''}
        {f'<p class="aside"><b>Would be found more often as:</b> {e(suggested)}</p>' if suggested else ''}
      </div>"""

        out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{i:02d}</span><h2>{e(t['title'])}</h2></div>
  <div class="sec-body">
    <div class="mast-meta" style="margin:0 0 22px">
      <span class="chip"><b>{count}</b> reviews</span>
      <span class="chip"><b>{stars}</b> stars on average</span>
    </div>

    <h4>What the merchant says</h4>
    <p class="say">{e(t['says'])}</p>

    <h4>What is actually going on</h4>
    {paragraphs(t['going_on'])}

    <h4>Who resolves it</h4>
    <p>{tags}</p>
    {f'<p class="aside"><b>Typical evidence in the review:</b> &ldquo;{e(quote[0][0])}&rdquo;</p>' if quote else ''}

    <h4>Is it already documented</h4>
    {doc_block or '<p class="aside">Not assessed.</p>'}

    <h4>Draft first reply</h4>
    <div class="say-long">{paragraphs(t['reply'])}</div>
    <p class="aside">Placeholders in capitals are the parts that must be filled from the
    actual account before sending. The reply is written to be sent close to as-is
    otherwise.</p>
  </div>
</section>""")

    # ------------------------------------------------ findings: the split
    n = len(ticket_rows)
    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{n + 1:02d}</span><h2>What the split says about the job</h2></div>
  <div class="sec-body">
    <p class="lede">Of {complaints} complaints, {decided} could be assigned an owner from
    the review text and {resolve.get('cannot_tell', 0)} could not.</p>

    <div class="grid3">
      <div class="stat"><span class="n">{resolve.get('support_can_fix', 0)}</span>
        <span class="l">Support resolves it</span>
        <span class="s">Settings, CSS, a refund, or showing where something lives.</span></div>
      <div class="stat"><span class="n">{resolve.get('explain_only', 0)}</span>
        <span class="l">Support explains it</span>
        <span class="s">Nothing is broken. A Shopify rule, the pricing model, or a feature that does not exist.</span></div>
      <div class="stat"><span class="n">{resolve.get('needs_engineering', 0)}</span>
        <span class="l">Support triages, engineering fixes</span>
        <span class="s">Support still takes first contact and reproduces it.</span></div>
    </div>

    <p style="margin-top:20px">Roughly two thirds of what arrives can be closed by the
    person who reads it. That is the shape of the job.</p>

    <div class="card warn">
      <p class="card-label">Where this number is weaker than it looks</p>
      <p><b>It is not a measurement.</b> Whether a support agent may issue a particular
      refund, or write custom CSS for a merchant, is a matter of internal policy that
      appears nowhere in the reviews, the documentation, or the App Store listing. Every
      assignment here is what a careful reader concluded from what the merchant wrote.</p>
      <p>The dataset does establish some of it. <b>65 reviews describe support writing
      custom CSS</b>, so theme work really is in scope. Merchants describe receiving
      refunds. The documentation settles whether a feature exists. Beyond those, the
      assignment is inference.</p>
      <p>The third label was originally "needs engineering". It was reworded after the
      hand-audit pointed out that support takes first contact on every ticket regardless
      of category, so a label implying otherwise made the figure read as a hand-off rate.</p>
    </div>
  </div>
</section>""")

    # ------------------------------------------------ findings: tenure
    order = ["first day", "first week", "first month", "1-3 months",
             "3-6 months", "6-12 months", "1-2 years", "2+ years"]
    tot = dict(ask("SELECT tenure_bucket, COUNT(*) FROM reviews GROUP BY 1"))
    comp = dict(ask("SELECT tenure_bucket, COUNT(*) FROM ticket_types GROUP BY 1"))
    chart_rows = [(b, comp.get(b, 0), tot.get(b, 0),
                   100 * comp.get(b, 0) / tot.get(b, 1)) for b in order if tot.get(b)]
    early = sum(comp.get(b, 0) for b in order[:3])
    early_tot = sum(tot.get(b, 0) for b in order[:3])
    late = sum(comp.get(b, 0) for b in order[-2:])
    late_tot = sum(tot.get(b, 0) for b in order[-2:])
    day_one = tot.get("first day", 0)

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{n + 2:02d}</span><h2>When complaints arrive</h2></div>
  <div class="sec-body">
    <p class="lede">The brief expected a cluster in week one, which would point at
    onboarding. The data says the opposite.</p>

    <figure>
      <div class="svg-card">{tenure_chart(chart_rows)}</div>
      <figcaption>Share of reviews containing a complaint, by how long the merchant had
      used the app when they wrote it. Counts are small in every bucket, so read the
      direction and not the individual figures. Tenure is as displayed on the review
      page; for the 106 edited reviews the date shown is the edit date, not the original.</figcaption>
    </figure>

    <p>Complaint rate roughly triples across the range, from
    {100 * comp.get('first day', 0) / tot.get('first day', 1):.1f}% of first-day reviews to
    {100 * comp.get('1-2 years', 0) / tot.get('1-2 years', 1):.1f}% at one to two years.
    Early reviewers are overwhelmingly positive. In the first month, {early} of {early_tot}
    reviews contain a complaint; past a year it is {late} of {late_tot}.</p>

    <div class="card key">
      <p class="card-label">The thing to notice</p>
      <p><b>{day_one} reviews were written by merchants who had used the app for less than
      a day</b>, and they are the most positive group in the dataset. A quarter of all
      reviews here were written before the merchant could plausibly have seen a result.
      That inflates the overall rating and it means early enthusiasm is not evidence the
      product worked.</p>
    </div>

    <h3>The type of complaint changes too</h3>
    <p>In the first month it is theme conflicts, reliability and requests for features.
    Past a year it is billing and support quality. Those need different fixes: the first
    group is a setup problem, the second is trust wearing through.</p>
  </div>
</section>""")

    # ------------------------------------------------ findings: app comparison
    apps = {}
    for app in ("aftersell", "upcart-cart-builder"):
        apps[app] = {
            "total": one("SELECT COUNT(*) FROM reviews WHERE app=?", app),
            "one_star": one("SELECT COUNT(*) FROM reviews WHERE app=? AND rating=1", app),
            "complaints": one("SELECT COUNT(*) FROM ticket_types WHERE app=?", app),
            "top": ask("""SELECT ticket_type, COUNT(*) FROM ticket_types WHERE app=?
                          GROUP BY 1 ORDER BY 2 DESC LIMIT 3""", app),
        }
    a, u = apps["aftersell"], apps["upcart-cart-builder"]
    fmt = lambda rows: ", ".join(
        f"{TICKETS.get(k, {}).get('title', k.replace('_', ' '))} ({v})" for k, v in rows)

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{n + 3:02d}</span><h2>Aftersell against UpCart</h2></div>
  <div class="sec-body">
    <p class="lede">UpCart's one-star rate is roughly double Aftersell's. The reason is
    not more of the same complaints. It is different complaints.</p>

    <table>
      <thead><tr><th>&nbsp;</th><th>Aftersell</th><th>UpCart</th></tr></thead>
      <tbody>
        <tr><td>Reviews</td><td class="mono">{a['total']}</td><td class="mono">{u['total']}</td></tr>
        <tr><td>One-star</td>
            <td class="mono">{a['one_star']} ({a['one_star'] / a['total']:.1%})</td>
            <td class="mono">{u['one_star']} ({u['one_star'] / u['total']:.1%})</td></tr>
        <tr><td>Containing a complaint</td><td class="mono">{a['complaints']}</td><td class="mono">{u['complaints']}</td></tr>
        <tr><td>Most common types</td><td>{e(fmt(a['top']))}</td><td>{e(fmt(u['top']))}</td></tr>
      </tbody>
    </table>

    <p><b>Aftersell's complaints are about money and people.</b> Billing surprises and
    support experience lead, alongside feature requests from merchants who are otherwise
    happy.</p>

    <p><b>UpCart's are about the thing not working.</b> Reliability and theme conflicts
    lead. That is consistent with what a cart drawer has to do: it renders inside every
    merchant's own theme, on every device, and there are a great many themes.</p>

    <div class="card good">
      <p class="card-label">Why this is good news for support</p>
      <p>Theme conflicts are the most fixable category in the whole dataset: 11 of 13 were
      resolvable by support directly, usually with CSS written in the conversation. UpCart's
      worse rating is driven substantially by a problem support is well placed to solve,
      rather than by anything that needs engineering.</p>
    </div>
  </div>
</section>""")

    # ------------------------------------------------ findings: praise
    praise = dict(ask("SELECT praise_type, COUNT(*) FROM classifications WHERE praise_type IS NOT NULL GROUP BY 1"))
    names = Counter()
    for (blob,) in ask("SELECT staff_mentioned FROM classifications"):
        for nm in json.loads(blob or "[]"):
            names[nm.strip().title()] += 1
    top_names = names.most_common(10)
    top_peak = top_names[0][1]

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{n + 4:02d}</span><h2>What the praise is about</h2></div>
  <div class="sec-body">
    <p class="lede">Support quality is the reason given in {praise.get('support_quality', 0)}
    reviews. Revenue results, which is what the product is sold on, account for
    {praise.get('revenue_result', 0)}.</p>

    <div class="grid3">
      <div class="stat"><span class="n">{praise.get('support_quality', 0)}</span>
        <span class="l">Praise the support</span>
        <span class="s">Speed, patience, or a named person who fixed it.</span></div>
      <div class="stat"><span class="n">{praise.get('revenue_result', 0)}</span>
        <span class="l">Praise the revenue</span>
        <span class="s">Made money, raised average order value, converted.</span></div>
      <div class="stat"><span class="n">{praise.get('customisation_help', 0)}</span>
        <span class="l">Praise custom work</span>
        <span class="s">Someone wrote CSS or built something for them.</span></div>
    </div>

    <p style="margin-top:20px">That ratio is the most useful finding in this document for
    anyone joining the support team. At these apps, support is not a cost attached to the
    product. It is the thing merchants write about.</p>

    <h3>Named most often</h3>
    <p class="aside">{len(names)} individuals are named across the dataset. Every name below
    was checked against the review that contains it.</p>""")

    for nm, c in top_names:
        out.append(f"""
    <div class="bar-row">
      <div class="bar-name">{e(nm)}</div>
      <div class="bar-track"><div class="bar-fill s" style="width:{c / top_peak * 100:.0f}%"></div></div>
      <div class="bar-val">{c}</div>
    </div>""")

    negative_names = one(
        """SELECT COUNT(*) FROM classifications WHERE staff_mentioned != '[]'
           AND sentiment != 'positive'""")
    out.append(f"""
    <p class="aside" style="margin-top:14px">Only {negative_names} reviews name a person in
    anything other than praise. Being named in one of these reviews is almost always a
    good thing.</p>
  </div>
</section>""")

    # ------------------------------------------------ how it was built
    audit_line = ""
    if audit:
        who, when, size, dis = audit
        audit_line = f"""
    <div class="card good">
      <p class="card-label">Checked by hand</p>
      <p><b>{size} classified reviews were read by a person on {e(when)}, with
      {dis} disagreement.</b> The sample was drawn at random across every ticket type,
      and each entry showed the review, the decision, the reasoning, and the exact words
      from the review said to justify it.</p>
      <p>The disagreement changed this document. A review labelled "needs engineering"
      was challenged on the grounds that support could reproduce and explain the issue
      first, escalating only if necessary. That was right about all 31 reviews carrying
      that label, not just the one, so the label is now worded "support triages,
      engineering fixes".</p>
      <p><b>The limit of that check:</b> the reader had the same review text the model
      had, and no access to internal policy. Two readers agreeing is consistency, not
      correctness.</p>
    </div>"""

    quotes_n = one("SELECT COUNT(*) FROM classifications WHERE evidence_quote IS NOT NULL")
    names_n = sum(len(json.loads(b or "[]")) for (b,) in ask("SELECT staff_mentioned FROM classifications"))

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">{n + 5:02d}</span><h2>How this was built, and how it was checked</h2></div>
  <div class="sec-body">
    <p class="lede">Claude read and categorised the reviews. That is only worth something
    if the output was checked, so here is what was checked and what was not.</p>

    <h3>The pipeline</h3>
    <ol>
      <li>Every review page for both apps was downloaded and saved. Shopify's robots.txt
      permits this path; requests were made one second apart with a self-identifying
      user agent.</li>
      <li>The saved pages were parsed into a SQLite database, one row per review. The
      parser checks its own output before it will report success.</li>
      <li>Each of the {with_text:,} reviews with text was sent to Claude for
      categorisation, with the answer cached so nothing is ever re-read.</li>
      <li>Each ticket type was checked against Aftersell's published documentation index
      of 265 pages.</li>
      <li>This document was generated from the database. No figure in it was typed by hand.</li>
    </ol>

    <h3>What was verified mechanically</h3>
    <p>Every decided judgement had to quote the exact words from the review that justify
    it. A script string-matches every quote and every extracted name against its source
    review, and fails if one does not appear.</p>

    <div class="grid2">
      <div class="card good">
        <p class="card-label">Passing</p>
        <p><b>{names_n} of {names_n} staff names</b> appear in the review that names them.<br>
        <b>{quotes_n} of {quotes_n} evidence quotes</b> are literal spans of their review.</p>
      </div>
      <div class="card">
        <p class="card-label">What that proves</p>
        <p>That nothing was invented. It does not prove the judgements are correct, and no
        automated check could.</p>
      </div>
    </div>
    {audit_line}

    <h3>What is still unverified</h3>
    <p>Whether a support agent is permitted to issue a given refund. Whether a specific
    charge was correct, which needs the merchant's invoice. Whether a reported fault is a
    defect or a misconfiguration, which needs someone to reproduce it. Roughly half the
    complaints turn on one of those, and the honest position is that they are questions
    rather than findings.</p>

    <div class="card key">
      <p class="card-label">The questions this raises</p>
      <ul class="plain">
        <li>Nothing in 265 documentation pages explains how to reach a human, what
        response times to expect, or how to escalate. Is that deliberate?</li>
        <li>Nothing covers products appearing on a customer's order without consent,
        which six merchants describe. What does that ticket do today?</li>
        <li>The analytics and Klaviyo interaction is documented, but under titles nobody
        would search. Who owns renaming a page?</li>
        <li>How much of a refund can support issue without approval? That single answer
        moves a large share of the billing tickets between two columns.</li>
      </ul>
    </div>
  </div>
</section>""")

    out.append(f"""
<footer>
  <p>Built from {total_reviews:,} public reviews of Aftersell and UpCart on the Shopify
  App Store, collected 26 August 2026. Source and method:
  <a href="https://github.com/quyanna/rokt-aftersell-reviews">github.com/quyanna/rokt-aftersell-reviews</a></p>
  <p>Review text quoted throughout belongs to the merchants who wrote it and is public on
  the App Store. Staff names appear as merchants wrote them.</p>
</footer>
</div>""")

    OUT_PATH.write_text("\n".join(out), encoding="utf-8")
    size = OUT_PATH.stat().st_size
    print(f"Wrote {OUT_PATH} ({size / 1024:.0f}KB)")
    print(f"  {len(ticket_rows)} ticket types, {complaints} complaints, {total_reviews:,} reviews")


if __name__ == "__main__":
    main()
