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
uv run fetch.py
```

That is stage 1. Later stages get added as they are built.

## The five stages

| Stage | Script | What it does | Status |
|---|---|---|---|
| 1 | `fetch.py` | Downloads every review page and saves the raw HTML | Done |
| 2 | `parse.py` | Pulls the reviews out of the HTML into a SQLite database | Not started |
| 3 | `classify.py` | Has Claude categorise each review, then hand-checks its work | Not started |
| 4 | `docs_match.py` | Checks each complaint against Aftersell's own help docs | Not started |
| 5 | `report.py` | Builds the triage sheet as a single HTML page | Not started |

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

## Working with AI on this project

Claude is used two different ways here, and the distinction matters.

It wrote most of the code. I read every line before running it, and where the
generated code was wrong I fixed it. Those fixes are logged in [NOTES.md](NOTES.md),
including three bugs in the first draft of `fetch.py`.

It also classifies the reviews in stage 3, and that is the part where taking the
output on trust would be a real mistake. So stage 3 includes a hand-audit: I label a
random sample of reviews myself, without looking at what the model said, then compare
the two. The agreement rate and every disagreement go into `NOTES.md` and into the
final report. Without that step there would be no way to tell you how often the
labels are wrong.

## Files

```
fetch.py      stage 1, the downloader
NOTES.md      decision log: every judgement call and why
data/         scraped pages and derived data, not committed, regenerate with fetch.py
```

## No secrets in this repo

Stage 3 needs an Anthropic API key. The scripts read it from the `ANTHROPIC_API_KEY`
environment variable and never write it to a file in this project. `.gitignore` covers
`data/` and `.env`, and it was committed before any data existed, because deleting a
file from git later does not remove it from the history.
