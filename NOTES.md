# Decision log

Written while the project was being built rather than reconstructed at the end. One
entry per stage, covering what was decided, what was rejected, and what the data would
not support.

Plain language throughout. This is meant to be readable by someone who does not write
code.

---

## Stage 1: collecting the review pages

Date: 26 August 2026

### What this stage does

Downloads all 177 pages of reviews across both apps and saves each page to disk
exactly as the server sent it. It makes no attempt to understand them. That is stage 2.

### Why downloading and parsing are separate steps

Pulling structured data out of a web page is finicky work, and the code that does it
is always wrong on the first attempt. Some review has an emoji in the store name, or a
missing country, or a date in a format you did not expect.

If downloading and parsing were one step, every parser bug would mean re-downloading
177 pages to test the fix. Splitting them means the parser gets tested against files
already sitting on disk, instantly and for free, as many times as needed. Shopify's
servers get hit exactly once.

### Checking this was allowed before writing any code

`apps.shopify.com/robots.txt` is the file websites use to tell automated tools what
they may and may not read. It explicitly permits `/reviews`. The paths it blocks are
`/internal/`, `/services/`, search queries and login parameters.

No crawl-delay is specified. I used one second between requests anyway, which is
slower than a human clicking "next page", and the whole job is about 180 requests, run
once. The script identifies itself by name in its User-Agent header and includes a
contact email rather than pretending to be a browser. All of the data is public, with
no login and no paywall in front of it.

### Decisions taken

#### Find out how many pages there are instead of guessing

The obvious approach is to keep requesting pages until one comes back empty. That has
a nasty failure mode. If the server ever returns an error page that still reports
success, the script would treat it as the end of the list and quietly stop 40 pages
early. Because finished pages are skipped on re-runs, that gap would then become
permanent and invisible.

Instead the script reads page 1 for its own pagination links, which include the last
page number, and announces "91 pages to collect" before it starts. If that number were
ever wrong it would be obvious immediately.

#### Refuse to save a page containing zero reviews

Same reasoning. An empty file on disk becomes a permanent hole in the dataset, because
re-runs skip files that already exist. Better to stop with a loud error.

#### No `--force` flag to re-download

To re-fetch a page, delete the file. To re-fetch an app, delete its folder. A
command-line flag would be a second way to do something that deleting a file already
does, and one more thing to have to remember in three months.

#### No external libraries for this stage

This step makes one web request with one custom header and saves the result. Python's
built-in tools do that in about six lines. Libraries like `requests` are nicer to use,
but every dependency you add is something that can break later. Stages 2 and 3 will
need real libraries. This one does not.

#### Locate reviews by the `data-merchant-review` attribute, never by CSS class

The class names on these pages are generated utility classes, long strings like
`tw-flex tw-mb-md tw-text-fg-primary`, and they change whenever the site is restyled.
The `data-merchant-review` attribute is a deliberate hook and is far more stable.

### Corrections made to AI-written code

Claude generated the first draft of `fetch.py`. Three things in it were wrong and were
fixed before the script was ever run.

The cached and downloaded counters were wrong for page 1. The code checked whether the
page-1 file existed after saving it, so a freshly downloaded page 1 was always reported
as "already on disk". This is cosmetic, but the summary line is what you use to confirm
the run did what you expected, so it needs to be right.

A bad app slug left an empty folder behind. The output folder was created before the
first request, so a typo in the app name created `data/raw/typo-name/` and then failed.
I moved the folder creation to after the first successful response.

A bad app slug also produced a 12-line Python stack trace. It now prints a plain
message instead: "404 Not Found, check the app slug, it is the part of the App Store
URL after apps.shopify.com/". Anyone reading over your shoulder should be able to tell
what went wrong.

### Results

| App | Pages | Reviews |
|---|---|---|
| `aftersell` | 91 | 905 |
| `upcart-cart-builder` | 86 | 860 |
| Total | 177 | 1,765 |

About 43MB on disk, and roughly 3 minutes of wall-clock time, almost all of it the
deliberate one-second wait between requests.

### Verified

Re-running the whole thing finishes in 0.13 seconds and makes no web requests.
Deleting a single page file causes exactly that one page to be re-downloaded. A
made-up app slug fails in 0.3 seconds with a readable message and leaves nothing
behind on disk. I spot-checked a page from the middle of the set and found 10 reviews,
as expected.

### Known limitations of this stage

This is a snapshot. Reviews posted after 26 August 2026 are not included, and a
merchant who edits or deletes a review later will not be reflected. The review counts
were slightly lower when the project was first scoped a few days earlier, so the pages
do keep moving.

The one-second delay is a courtesy rather than a requirement. If Shopify ever adds a
crawl-delay to their robots.txt, this script does not read it and would need updating.
