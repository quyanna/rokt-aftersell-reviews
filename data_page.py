# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Builds the companion page: the underlying data, readable rather than downloadable.

Reads   data/reviews.db, assets/brief.css
Writes  data.html

The triage sheet argues; this page shows its working. Every complaint appears in
full, with the review text, every field the classifier produced, and the exact
words it quoted as evidence. Nothing is summarised away.

Usage:
    uv run data_page.py
"""

import html
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "reviews.db"
CSS_PATH = HERE / "assets" / "brief.css"
OUT_PATH = HERE / "docs" / "data.html"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:'
    'opsz,wdth,wght@12..96,75..100,300..800&family=Newsreader:ital,opsz,wght@'
    '0,6..72,300..700;1,6..72,300..600&family=JetBrains+Mono:wght@400;500;700'
    '&display=swap" rel="stylesheet">'
)

RESOLVE = {
    "support_can_fix": ("Support resolves it", "t-strong"),
    "explain_only": ("Support explains it", "t-mid"),
    "needs_engineering": ("Support triages, engineering fixes", "t-gap"),
    "cannot_tell": ("Not decidable", ""),
}

# Filtering and the row counter are the only script on the page. Everything else
# is static, so the page still reads correctly with JavaScript turned off.
SCRIPT = """
<script>
(function () {
  var box = document.getElementById('q');
  var sel = document.getElementById('type');
  var rows = Array.prototype.slice.call(document.querySelectorAll('[data-row]'));
  var count = document.getElementById('count');
  function apply() {
    var q = box.value.toLowerCase().trim();
    var t = sel.value;
    var shown = 0;
    rows.forEach(function (r) {
      var okType = (t === '*' || r.getAttribute('data-type') === t);
      var okText = (q === '' || r.getAttribute('data-search').indexOf(q) !== -1);
      var show = okType && okText;
      r.style.display = show ? '' : 'none';
      if (show) shown++;
    });
    count.textContent = shown + (shown === 1 ? ' review' : ' reviews');
  }
  box.addEventListener('input', apply);
  sel.addEventListener('change', apply);
  apply();
})();
</script>
"""

EXTRA_CSS = """
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:22px 0 10px;
  position:sticky;top:0;background:var(--paper);padding:14px 0;z-index:5;
  border-bottom:1px solid var(--rule)}
.filters input,.filters select{font-family:var(--mono);font-size:12px;padding:8px 10px;
  border:1px solid var(--rule);background:var(--surface);border-radius:2px;color:var(--ink)}
.filters input{flex:1;min-width:200px}
#count{font-family:var(--mono);font-size:11px;color:var(--ink3);letter-spacing:.06em}
.row{border-bottom:1px solid var(--rule-soft);padding:20px 0}
.row-meta{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;color:var(--ink3);
  margin-bottom:8px;display:flex;flex-wrap:wrap;gap:12px}
.row-body{font-size:16px;line-height:1.55;margin:0 0 12px;max-width:70ch}
.row-fields{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.q-ev{font-family:var(--mono);font-size:12.5px;color:var(--teal);
  border-left:2px solid var(--teal-line);padding-left:12px;margin:8px 0;max-width:66ch}
.brandon{background:var(--mag-soft);border:1px solid var(--mag-line);border-radius:3px;
  padding:16px 18px;margin:14px 0}
.brandon .row-body{margin-bottom:6px}
.stars{color:var(--mag);letter-spacing:2px}
pre{background:var(--surface);border:1px solid var(--rule);border-radius:3px;
  padding:16px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.6}
"""


def e(text):
    return html.escape(str(text or ""))


def main():
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} is missing. Run the earlier stages first.")
    db = sqlite3.connect(DB_PATH)
    ask = lambda sql, *a: db.execute(sql, a).fetchall()
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]

    total = one("SELECT COUNT(*) FROM reviews")
    classified = one("SELECT COUNT(*) FROM classifications")
    complaints = one("SELECT COUNT(*) FROM ticket_types")

    out = [f"<title>The data behind the triage sheet</title>{FONTS}",
           f"<style>{CSS_PATH.read_text(encoding='utf-8')}{EXTRA_CSS}</style>",
           '<div class="wrap">']

    out.append(f"""
<header class="mast">
  <p class="eyebrow">Companion to the triage sheet</p>
  <h1>The data, <em>shown</em> rather than summarised</h1>
  <p class="standfirst">Every complaint in the dataset, in full, with the review text and
  every field the classifier produced from it. The triage sheet makes the argument. This
  page is where you check it.</p>
  <div class="mast-meta">
    <span class="chip"><b>{total:,}</b> reviews collected</span>
    <span class="chip"><b>{classified:,}</b> classified</span>
    <span class="chip"><b>{complaints}</b> contain a complaint</span>
    <span class="chip"><a href="index.html">Back to the triage sheet</a></span>
  </div>
</header>""")

    # ---------------------------------------------------------------- schema
    tables = ask("""SELECT name FROM sqlite_master WHERE type IN ('table','view')
                    AND name NOT LIKE 'sqlite_%' ORDER BY name""")
    rows_html = ""
    for (t,) in tables:
        n = one(f"SELECT COUNT(*) FROM {t}")
        cols = ", ".join(c[1] for c in ask(f"PRAGMA table_info({t})"))
        rows_html += (f"<tr><td class='mono'>{e(t)}</td><td class='mono'>{n:,}</td>"
                      f"<td style='font-size:13px'>{e(cols)}</td></tr>")

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">01</span><h2>Query it yourself</h2></div>
  <div class="sec-body">
    <p class="lede">Everything here comes from one SQLite file. No server, no setup: open
    it and write SQL.</p>
    <pre>git clone https://github.com/quyanna/rokt-aftersell-reviews
cd rokt-aftersell-reviews
./run.sh                      # rebuilds data/reviews.db from scratch

sqlite3 data/reviews.db
sqlite&gt; SELECT ticket_type, COUNT(*) FROM ticket_types GROUP BY 1 ORDER BY 2 DESC;</pre>
    <table>
      <thead><tr><th>Table</th><th>Rows</th><th>Columns</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p class="aside"><b>ticket_types</b> is a view, not a table. It turns the classifier's
    fields into the categories the report uses, by a rule kept in
    <span class="mono">ticket_types.sql</span> so it can be read and argued with rather
    than taken on trust.</p>
  </div>
</section>""")

    # ------------------------------------------------------------- every complaint
    types = [t for (t,) in ask("""SELECT ticket_type FROM ticket_types
                                  GROUP BY 1 ORDER BY COUNT(*) DESC""")]
    options = "".join(f'<option value="{e(t)}">{e(t.replace("_", " "))}</option>' for t in types)

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">02</span><h2>Every complaint, in full</h2></div>
  <div class="sec-body">
    <p class="lede">All {complaints} of them. Nothing is trimmed, and the evidence quote
    beneath each one is the exact span of the review the classifier said justified its
    decision.</p>

    <div class="filters">
      <input id="q" type="search" placeholder="Search the review text, store, or country">
      <select id="type"><option value="*">Every ticket type</option>{options}</select>
      <span id="count"></span>
    </div>""")

    for (rid, app, rating, date, store, country, tenure, body, ticket, resolvability,
         reason, quote, secondary, support_failure, confidence, wanted) in ask("""
        SELECT r.review_id, r.app, r.rating, r.review_date, r.store_name, r.country,
               r.tenure_raw, r.body, t.ticket_type, c.resolvability,
               c.resolvability_reason, c.evidence_quote, c.secondary_complaint,
               c.support_failure, c.confidence, c.wanted
        FROM ticket_types t JOIN reviews r USING(review_id)
        JOIN classifications c USING(review_id)
        ORDER BY r.rating, r.review_date DESC"""):

        search = " ".join(str(x or "").lower() for x in (body, store, country, ticket))
        label, cls = RESOLVE.get(resolvability, (resolvability or "", ""))
        fields = [f'<span class="tag t-mid">{e(ticket.replace("_", " "))}</span>']
        if label:
            fields.append(f'<span class="tag {cls}">{e(label)}</span>')
        if secondary:
            fields.append(f'<span class="tag">also: {e(secondary.replace("_", " "))}</span>')
        if support_failure:
            fields.append('<span class="tag t-gap">support let them down</span>')

        out.append(f"""
    <div class="row" data-row data-type="{e(ticket)}" data-search="{e(search)}">
      <div class="row-meta">
        <span class="stars">{"&#9733;" * rating}{"&#9734;" * (5 - rating)}</span>
        <span>{e(store)} &middot; {e(country)}</span>
        <span>{e(app)}</span>
        <span>{e(tenure or "tenure not stated")}</span>
        <span>{e(date)}</span>
        <span>#{rid}</span>
      </div>
      <p class="row-body">{e(" ".join(body.split()))}</p>
      <div class="row-fields">{"".join(fields)}</div>
      {f'<p class="q-ev">evidence: &ldquo;{e(quote)}&rdquo;</p>' if quote else ''}
      <p class="aside" style="font-size:14px">{e(reason or wanted)}
      <span class="mono" style="color:var(--ink3)"> &middot; confidence {e(confidence)}</span></p>
    </div>""")

    out.append("</div></section>")

    # ------------------------------------------------------------------- Brandon
    brandon = ask("""SELECT r.rating, r.review_date, r.store_name, r.country, r.app, r.body
                     FROM classifications c JOIN reviews r USING(review_id)
                     WHERE c.staff_mentioned LIKE '%randon%'
                     ORDER BY r.review_date""")
    if brandon:
        ratings = [b[0] for b in brandon]
        best = max(brandon, key=lambda b: 0 if len(b[5]) > 60 else 1)
        countries = len({b[3] for b in brandon})
        out.append(f"""
<section id="brandon">
  <div class="sec-head"><span class="sec-num">03</span><h2>A note on Brandon</h2></div>
  <div class="sec-body">
    <p class="lede">While counting which support staff merchants name most often, one
    name came up {len(brandon)} times. Every single one is a five-star review. It seemed
    rude not to mention it.</p>

    <div class="grid3">
      <div class="stat"><span class="n">{len(brandon)}</span>
        <span class="l">Reviews naming Brandon</span>
        <span class="s">Across both apps.</span></div>
      <div class="stat"><span class="n">{sum(ratings) / len(ratings):.1f}</span>
        <span class="l">Average rating</span>
        <span class="s">Out of five. There is no rounding happening here.</span></div>
      <div class="stat"><span class="n">{countries}</span>
        <span class="l">Countries</span>
        <span class="s">Including one review written in Norwegian.</span></div>
    </div>

    <p style="margin-top:20px">The shortest of them, quoted in full, from a merchant in
    Germany:</p>
    <p class="say">Brandon need to get more money 100%</p>
    <p class="aside">This document takes no position on that, other than to note the
    merchant was quite clear.</p>

    <h3>All {len(brandon)}</h3>""")
        for rating, date, store, country, app, body in brandon:
            out.append(f"""
    <div class="brandon">
      <div class="row-meta">
        <span class="stars">{"&#9733;" * rating}</span>
        <span>{e(store)} &middot; {e(country)}</span>
        <span>{e(app)}</span>
        <span>{e(date)}</span>
      </div>
      <p class="row-body">{e(" ".join(body.split()))}</p>
    </div>""")
        out.append("""
    <p class="aside">Names were extracted by the classifier and then checked
    automatically: every name in this dataset appears in the review that names it. None
    of these were invented, including that one.</p>
  </div>
</section>""")

    # -------------------------------------------------------------- everyone named
    names = Counter()
    for (blob,) in ask("SELECT staff_mentioned FROM classifications"):
        for nm in json.loads(blob or "[]"):
            names[nm.strip().title()] += 1
    listed = names.most_common()
    peak = listed[0][1]
    body_rows = "".join(
        f'<tr><td>{e(nm)}</td><td class="mono">{c}</td>'
        f'<td><div class="bar-track" style="max-width:220px">'
        f'<div class="bar-fill s" style="width:{c / peak * 100:.0f}%"></div></div></td></tr>'
        for nm, c in listed if c > 1
    )
    once = sum(1 for _, c in listed if c == 1)

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">04</span><h2>Everyone merchants named</h2></div>
  <div class="sec-body">
    <p class="lede">{len(listed)} individuals are named across the dataset. {len(listed) - once}
    are named more than once; {once} appear a single time.</p>
    <table>
      <thead><tr><th>Name</th><th>Mentions</th><th>&nbsp;</th></tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
    <p class="aside">Spelling and capitalisation are as merchants wrote them, normalised
    only for case. Near-duplicates such as a misspelled name were left alone rather than
    merged automatically, since guessing which of two spellings is a typo is not something
    to do silently.</p>
  </div>
</section>""")

    # ------------------------------------------------------------------ breakdowns
    def table(title, rows, headers):
        body = "".join(
            "<tr>" + "".join(f'<td{" class=\'mono\'" if i else ""}>{e(c)}</td>'
                             for i, c in enumerate(r)) + "</tr>" for r in rows)
        head = "".join(f"<th>{e(h)}</th>" for h in headers)
        return f"<h3>{e(title)}</h3><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    out.append(f"""
<section>
  <div class="sec-head"><span class="sec-num">05</span><h2>Counts</h2></div>
  <div class="sec-body">
    {table("Reviews by app and rating",
           ask('''SELECT app, rating, COUNT(*) FROM reviews GROUP BY 1,2 ORDER BY 1, 2 DESC'''),
           ["App", "Rating", "Reviews"])}
    {table("Ticket types",
           ask('''SELECT ticket_type, COUNT(*), ROUND(AVG(rating),1) FROM ticket_types
                  GROUP BY 1 ORDER BY 2 DESC'''),
           ["Ticket type", "Count", "Mean stars"])}
    {table("Who resolves it",
           ask('''SELECT resolvability, COUNT(*) FROM ticket_types GROUP BY 1 ORDER BY 2 DESC'''),
           ["Resolvability", "Count"])}
    {table("What the praise is about",
           ask('''SELECT praise_type, COUNT(*) FROM classifications
                  WHERE praise_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC'''),
           ["Praise type", "Count"])}
    {table("Merchant tenure when the review was written",
           ask('''SELECT COALESCE(tenure_bucket,'not stated'), COUNT(*) FROM reviews
                  GROUP BY 1 ORDER BY MIN(COALESCE(tenure_months, 1e9))'''),
           ["Tenure", "Reviews"])}
    {table("Where merchants are",
           ask('''SELECT country, COUNT(*) c FROM reviews GROUP BY 1 ORDER BY c DESC LIMIT 15'''),
           ["Country", "Reviews"])}
    {table("Documentation coverage",
           ask('''SELECT complaint_type, tag FROM doc_coverage ORDER BY 1'''),
           ["Ticket type", "Coverage"])}
  </div>
</section>""")

    out.append(f"""
<footer>
  <p><a href="index.html">Back to the triage sheet</a> &middot;
  <a href="https://github.com/quyanna/rokt-aftersell-reviews">Source and method on GitHub</a></p>
  <p>Review text belongs to the merchants who wrote it and is public on the Shopify App
  Store. Collected 26 August 2026.</p>
</footer>
</div>
{SCRIPT}""")

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f}KB)")
    print(f"  {complaints} complaints listed, {len(listed)} names, {len(brandon)} Brandons")


if __name__ == "__main__":
    main()
