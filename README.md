# Shopify review → support triage sheet

Reads the public Shopify App Store reviews for Aftersell (post-purchase upsells) and
UpCart (cart drawer), then works out what a support person would actually have to do
about each recurring complaint.

This isn't market research. The question throughout is what would land in my ticket
queue, and what would stop it landing there.

Point it at any Shopify app slug and it works.

## The honest caveat, up front

People who quietly uninstall an app never write a review. This dataset measures loud
complaints rather than common ones. Real ticket volume would skew far more mundane:
password resets, questions about where a setting lives, billing queries that never
reach a public review page. Every number here should be read as "of the people angry
enough to post in public", never as "of merchants".

There are also only about 90 negative reviews across both apps. That is enough to
describe patterns. It is not enough for statistics, and nothing in this project claims
otherwise.

## How to run it

You need [uv](https://docs.astral.sh/uv/), a Python runner that installs its own
dependencies. There is nothing else to set up. No virtual environment, no
`pip install`.

```bash
./run.sh
```

That runs all six steps and writes `triage-sheet.html`. Every stage is incremental, so
re-running it costs nothing and repeats no work.

Stage 3 needs an Anthropic API key. Put it in a `.env` file as
`ANTHROPIC_API_KEY=...` or export it in your shell. Classifying all 1,559 reviews
costs a few dollars of API credit, paid once and then cached.

## The five stages

| Stage | Script | What it does | Status |
|---|---|---|---|
| 1 | `fetch.py` | Downloads every review page and saves the raw HTML | Done |
| 2 | `parse.py` | Pulls the reviews out of the HTML into a SQLite database | Done |
| 3 | `classify.py` | Has Claude categorise each review | Done |
| 3b | `sample.py` | Draws a readable sample of the answers to check by hand | Done, 41 reviewed |
| 3c | `verify.py` | Checks every quote and name against its source review | Passing |
| 4 | `docs_match.py` | Checks each complaint against Aftersell's own help docs | Done |
| 5 | `report.py` | Builds the triage sheet as a single HTML page | Done |

Each stage is a separate script on purpose. Pulling structured data out of a web page
is finicky and the code that does it is always wrong on the first attempt. Keeping the
download separate means those bugs get fixed against files already on disk instead of
by hitting Shopify's servers again.

Every stage is re-runnable and picks up where it left off. Nothing re-downloads or
re-classifies work that is already done, so running the whole pipeline a second time
should cost nothing.

## Stage 1: what was collected

| App | Pages | Reviews |
|---|---|---|
| `aftersell` | 91 | 905 |
| `upcart-cart-builder` | 86 | 860 |

That is about 43MB of raw HTML in `data/raw/`, one file per page.

The raw HTML is not in this repository. Running `fetch.py` regenerates it in about
three minutes. Committing 43MB of machine-generated markup that nobody will ever read
would make the repo slow to clone for no benefit.

### Was scraping this OK?

I checked before writing any code.

- `apps.shopify.com/robots.txt`, the file websites use to tell automated tools what
  they may read, explicitly permits `/reviews`. The paths it blocks are `/internal/`,
  `/services/`, search queries and authentication parameters.
- No crawl-delay is specified. The script waits a second between requests anyway,
  which is slower than a person clicking through the pages by hand.
- The script sends a User-Agent that names itself and includes a contact email, so
  Shopify can get in touch rather than having to guess who is doing this.
- The data is public. Anyone can read it in a browser without logging in.

The whole job is about 180 requests at one per second, run once. Re-runs make no
requests at all.

## Stage 2: what is in the database

`data/reviews.db` holds 1,765 reviews dated February 2020 to August 2026, one row
each, with the rating, date, full text, store name, country, how long the merchant had
used the app, and Rokt's reply where there is one. It is a plain SQLite file, so you
can query it directly.

| App | 1 star | 2 | 3 | 4 | 5 | Total |
|---|---|---|---|---|---|---|
| `aftersell` | 21 | 10 | 2 | 23 | 849 | 905 |
| `upcart-cart-builder` | 38 | 4 | 8 | 16 | 794 | 860 |

803 reviews (45%) got a reply from Rokt. 83 are negative, meaning 3 stars or fewer.

Two things about the data are worth knowing before trusting any number built on it.
For the 106 reviews marked as edited, the date shown is the date of the edit, and the
original date is not published anywhere. And 439 reviews, a quarter of the total, were
written by merchants who had used the app for less than a day, 97 of them within an
hour of installing.

`parse.py` checks its own output every time it runs, before printing anything. If the
site markup changes and the parser starts reading the wrong element, the build stops
rather than quietly producing a database that looks fine.

## Stage 3: what the reviews are about

124 reviews contain a complaint. Who could resolve them:

| | Count |
|---|---|
| Support could fix it | 45 |
| Support can only explain it | 44 |
| Needs engineering | 35 |

Every one of those rows records a sentence explaining why it was judged that way,
so the reasoning can be checked rather than taken on trust. What that judgement
does not know is covered below.

The most common complaints are a genuinely missing feature (32), a billing surprise
(21), the app crashing or freezing (18), and a theme conflict (15). A further 44
reviews complain about support quality alongside whatever else brought them there.

Fewer than two thirds of those complaints come from reviews rated 3 stars or below.
The rest are in 4 and 5 star reviews, from merchants who are happy overall and still
describe a problem. Classifying only the negatives, which was the original plan,
would have missed roughly four in ten of the complaints in this dataset.

**What the classifier was told, and what it was not.** It saw the app name, the star
rating, the merchant's tenure, and the review text. It did not read Aftersell's
documentation, did not see Rokt's public reply to the review, and has no knowledge
of what Rokt's support team is actually authorised to do. So "support could fix it"
means a careful reader concluded that from the review text. Whether an agent can in
fact issue that refund is a matter of Rokt's internal policy, which appears nowhere
in this dataset. [NOTES.md](NOTES.md) covers why Rokt's public replies were examined
as grounding and deliberately rejected.

Praise is overwhelmingly about people rather than software. Support quality is the
reason given in 971 reviews, against 136 for revenue results.

## Stage 4: does the documentation already cover it?

The question is not whether the docs mention a problem. It is whether the merchant
who wrote the review would have found the page. A detailed article explaining why
Apple Pay cannot trigger post-purchase upsells helps nobody if it is titled in words
no angry merchant would search for.

| | Complaint types | Reviews affected |
|---|---|---|
| Documented but buried | 4 | 58 |
| Documented and easy to find | 6 | 55 |
| Not documented | 2 | 20 |

Two things have no page at all. There is nothing explaining how to contact support,
what response times to expect, or how to escalate. And nothing covers products
appearing on customer orders without consent, which six reviews describe.

## Working with AI on this project

Claude is used two different ways here, and the distinction matters.

It wrote most of the code. I read every line before running it, and where the
generated code was wrong I fixed it. Those fixes are logged in [NOTES.md](NOTES.md).
The stage 2 entry is the one worth reading: a bug filled the country column with store
names in all 1,765 rows, and the printed summary looked entirely correct anyway. It
turned up only because I wrote a check for it.

It also classified all 1,559 reviews in stage 3, and that is the part where taking
the output on trust would be a real mistake. So `audit.py` shows me a sample spread
across every complaint type, one review at a time, without the model's answer,
records what I think, and then reports the agreement rate and every disagreement.

Two checks back that up, one mechanical and one human.

`verify.py` string-matches every extracted staff name and every evidence quote
against the review it came from. A fabricated quote fails and the script exits with
an error. It currently passes on 609 of 609 names and 109 of 109 quotes. That proves
nothing was invented. It does not prove the judgements are right, and the script
says so when it passes.

`sample.py` draws a stratified random sample and writes it to a numbered document
showing each review, the model's decision, its reasoning, and the exact words it says
justify that decision. 41 reviews were read this way on 26 August 2026, with one
disagreement. That disagreement changed the report: it showed the `needs_engineering`
label implied support does nothing, when support in fact takes first contact on every
ticket, so the label is now worded "support triages, engineering fixes". See
[NOTES.md](NOTES.md) and [resolvability_labels.md](resolvability_labels.md).

The limit of that audit is stated rather than glossed. The person reading the sample
had the same review text the model had and no access to Rokt's internal policies.
Two readers agreeing is consistency, not correctness.

## Files

```
fetch.py      stage 1, the downloader
parse.py      stage 2, HTML into SQLite, with built-in data checks
classify.py   stage 3, asks Claude to categorise every review
sample.py     stage 3b, writes a readable sample of the answers to check by hand
verify.py     stage 3c, proves every quote and name comes from its source review
docs_match.py stage 4, ticket types against the published doc index
report.py     stage 5, builds triage-sheet.html
tickets.py    the written analysis and draft replies, the hand-written half
ticket_types.sql  the rule that turns classifier fields into ticket types
run.sh        runs the whole pipeline
assets/       the stylesheet the report is built against
docs_match.py stage 4, complaint types against the published doc index
NOTES.md      decision log: every judgement call and why
data/         scraped pages and the database, not committed, regenerate with the scripts
```

## No secrets in this repo

Stage 3 needs an Anthropic API key. The scripts read it from the `ANTHROPIC_API_KEY`
environment variable and never write it to a file in this project. `.gitignore` covers
`data/` and `.env`, and it was committed before any data existed, because deleting a
file from git later does not remove it from the history.
