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

---

## Stage 2: parsing the pages into a database

Date: 26 August 2026

### What this stage does

Reads the 177 saved HTML files and writes one row per review into a single SQLite
file at `data/reviews.db`. SQLite needs no server and no setup, and the whole database
is one file you can copy, delete or query directly.

### Each review has an id, so page position is not the key

The pages carry a `data-review-content-id` on every review. That is Shopify's own
identifier and it stays the same no matter which page the review currently sits on.

This matters more than it looks. My original plan was to key rows on the combination
of app, page number and position on the page. That would have been wrong. New reviews
push older ones down the list, so a review that is fifth on page 3 today will be
somewhere else next month, and re-parsing after a re-fetch would have produced
duplicates and mismatched rows. Using the published id means re-parsing simply
overwrites the same row.

### Turning tenure text into a number

Shopify publishes how long a merchant had used the app as text, like "Over 1 year
using the app". Before deciding on a mapping I extracted every one of the 1,765
strings and counted the vocabulary rather than guessing at it. All of them match a
single pattern: an optional qualifier, a number, and a unit.

| Unit | Count | Qualifier | Count |
|---|---|---|---|
| minute | 97 | none | 1,059 |
| hour | 342 | About | 586 |
| day | 484 | Over | 93 |
| month | 637 | Almost | 26 |
| year | 204 | | |

There are no weeks and no "Less than". Every string parsed, and one review has no
tenure line at all.

The qualifier is deliberately thrown away. "Over 1 year", "About 1 year" and "Almost
1 year" all become 12 months. I could have multiplied "Over" by 1.25 and "Almost" by
0.92, but those numbers would be invented, and the qualifier carries at most a couple
of months of real information. The verbatim string is kept in a `tenure_raw` column so
anyone who wants to do better can.

A month is treated as a flat 30.44 days. This is for rough grouping, not arithmetic.

The number is not really the point. The question stage 5 needs to answer is whether
complaints cluster in the first week or after a year, so the column that matters is
`tenure_bucket`: first day, first week, first month, 1-3 months, 3-6 months, 6-12
months, 1-2 years, 2+ years.

### The database checks itself every time it is built

`parse.py` runs a set of assertions immediately after parsing, before it prints
anything. They check that every rating falls between 1 and 5, that every date parsed,
that no ids are duplicated, that the country column does not contain a store name or a
tenure string, that no developer reply has leaked into a review body, and that every
tenure string that exists also produced a number.

These live inside `parse.py` rather than in a separate test file so they cannot be
forgotten. If the site markup changes and the parser starts picking up the wrong
element, the build stops instead of quietly producing a plausible-looking database.

### Corrections made to AI-written code

The country column was being filled with the store name, in all 1,765 rows. The store
name, country and tenure sit in three plain `div` elements with nothing to tell them
apart, and my code took the first one that was not the tenure line. The first one is
the store name. The fix was to skip the div containing the store name element before
looking at the rest.

This one is worth dwelling on, because the summary output looked completely correct.
Review counts, star distribution, date range and tenure spread were all right. Nothing
about the printed output suggested a problem. The bug surfaced only because I wrote a
check comparing the country column against the store name column, which is not a
comparison anyone would think to make by eye. Reading the output is not the same as
checking the data.

### Two things that looked like bugs and were not

**206 reviews have no text at all.** They are almost all 5-star, and 123 of them still
got a reply from Rokt. Checking the raw HTML showed the paragraph element genuinely
empty, so these are merchants who left a star rating and wrote nothing. This is a real
finding about the dataset and not a parsing failure.

**29 reviews have a developer reply dated before the review itself.** Every one of
them is flagged as edited. Rokt replied, then the merchant went back and edited their
review, and the page now shows the date of that edit. This is exactly the limitation
recorded in the schema, showing up in the data.

### Results

1,765 reviews, dated 7 February 2020 to 26 August 2026.

| App | 1 star | 2 | 3 | 4 | 5 | Total |
|---|---|---|---|---|---|---|
| `aftersell` | 21 | 10 | 2 | 23 | 849 | 905 |
| `upcart-cart-builder` | 38 | 4 | 8 | 16 | 794 | 860 |

803 reviews (45%) have a reply from Rokt. 106 were edited. 83 are negative, meaning 3
stars or fewer, split 33 for Aftersell and 50 for UpCart.

UpCart's one-star rate is 4.4% against Aftersell's 2.3%, which confirms the roughly
double figure the project started from.

The tenure spread has one result worth carrying into stage 5. 439 reviews, a quarter
of the total, were written by merchants who had used the app for less than a day, and
97 of those within an hour of installing. A meaningful share of this dataset was
written before the merchant could plausibly have seen a result.

### Known limitations of this stage

For the 106 edited reviews, `review_date` is the date of the edit. The original date
is not published anywhere, so any analysis by date treats these as later than they
really were.

The tenure figure is what the page displays, which I have assumed is the merchant's
tenure at the time they wrote the review. Shopify does not document this, so it is an
assumption rather than a verified fact.
