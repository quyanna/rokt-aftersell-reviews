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

---

## Stage 3: classifying every review

Date: 26 August 2026

### What this stage does

Sends all 1,559 reviews that have text to Claude and asks it to categorise each
one: what the complaint is, whether support could resolve it, what the praise is
about, and which staff are named. The 206 reviews with a star rating and no text
are skipped, because there is nothing in them to classify.

Answers are cached by review id, so re-running costs nothing, and rows are written
as they arrive rather than at the end. Interrupting the run loses nothing.

Every answer is stored with the model's raw response next to it. Any number in the
final report can be traced back to exactly what the model said about a specific
review.

### The categories were built from the data, not assumed

The project started with seven categories written from reading a sample by hand.
Before writing the classifier I read all 77 negative reviews that have text. Three
things needed to change.

**Support quality came out of the category list and became its own yes/no field.**
This is the most important change. Complaints about slow or unhelpful support
appear alongside a different underlying problem in most negative reviews. If
support quality has to compete for a single category slot, one of the two signals
is destroyed: either the technical problem is hidden behind the support complaint,
or the support pattern disappears. As a separate flag both survive. 44 reviews
carry it.

**"Offer doesn't fire" split into two.** `offer_not_firing` for a funnel that does
not trigger, and `app_unreliable` for crashes, freezes, blank screens and lost
work. A support agent handles those differently: one is configuration, the other is
an escalation.

**Five categories the data had that the original list did not.**
`third_party_integration_broken` covers UpCart stopping Klaviyo from seeing
add-to-cart events, analytics double counting, and ad platform attribution
breaking. `unexpected_order_change` covers products appearing on customer orders
without consent and duplicate charges, which is the most serious class in the set.
`cancellation_or_uninstall_trouble` splits from billing because the reply is
completely different. `feature_missing` splits from `shopify_platform_limit`
because merchants constantly confuse a missing feature with a Shopify constraint
and support must not. `support_only` was added later, for the reason below.

### Corrections made to AI-written code

**The JSON schema was invalid and all 12 trial calls failed.** A field cannot
declare `enum` alongside a nullable type union like `["string", "null"]`. The two
cases have to be written as separate branches under `anyOf`.

What matters more than the bug is what happened around it. The run did not crash.
All 12 failures were recorded in a `classification_failures` table with the error
text, the script exited cleanly, and clearing that table made them retry. The
requirement that a malformed response must not kill a long run was tested by
accident on the first attempt, and held.

**A category gap that would have skewed the most important number.** In the trial,
the review "Worst customer support ever" came back with no complaint category and,
worse, no resolvability. Because support quality had deliberately been moved out of
the category list, reviews where support is the *entire* complaint had nowhere to
go, and a missing resolvability drops them out of the fix, explain or escalate
split. That split is the number the whole project is for.

The fix was a `support_only` category for reviews that name no underlying technical
or billing problem, plus an explicit rule that resolvability can never be empty
when a complaint exists. Responding faster is within support's control, so those
reviews belong in "support can fix".

This is why the trial ran on 12 reviews before spending money on 1,559.

### Results

1,559 reviews classified, no failures.

Who could resolve the 133 reviews that contain a complaint:

| | Count |
|---|---|
| Support could fix it | 52 |
| Support can only explain it | 47 |
| Needs engineering | 34 |

Complaint types, most common first: feature_missing 32, billing_surprise 21,
app_unreliable 18, theme_or_styling_conflict 15, support_only 14, other 9,
third_party_integration_broken 7, unexpected_order_change 6,
cancellation_or_uninstall_trouble 5, shopify_platform_limit 4, offer_not_firing 1,
no_measurable_return 1.

44 reviews mention a support failure alongside whatever else they came for.

What the praise is about: support quality 971, general approval 210, revenue
results 136, ease of setup 108, custom work done for them 65. Support quality is
mentioned in more than half of all reviews in the dataset.

### The finding that justifies classifying everything

Only 77 of the 133 complaints come from reviews rated 3 stars or below. **The other
56, more than four in ten, are in 4 and 5 star reviews.** Thirty-eight are in
5-star reviews: merchants who are happy overall and still describe a problem.

Had this project classified only the negatives, as originally planned, it would
have missed 42% of the complaints in its own dataset, and every one of those is a
ticket someone had to answer.

### The hand-audit has not been run yet

`audit.py` exists and is the reason any of these numbers should be believed. It
draws a sample spread across every complaint type, shows each review without the
model's answer, records a human judgement, and then reports the agreement rate and
prints every disagreement in full. The random seed is fixed so anyone re-running
gets the same sample.

At the time of writing it has not been run. Until it has, every figure in this
section is the model's opinion, unchecked. That is stated here rather than left for
someone to discover.

### Known limitations of this stage

The model was given the star rating alongside the text, which may pull its
sentiment judgement toward the rating rather than the words.

Staff names come back as the model read them, including case and spelling
variants. "Dom" and "DOM" appear separately, and "Lilllian" is almost certainly
"Lillian". Any leaderboard needs to normalise these, and near-matches should be
merged with care rather than automatically.

75 reviews were classified with low confidence, mostly very short ones. They are
kept, and the confidence field is stored so they can be excluded from any figure
where they would mislead.

---

## Stage 4: checking complaints against the documentation

Date: 26 August 2026

### What this stage does

Downloads the index of Aftersell's public docs from
`https://docs.aftersell.com/llms.txt`, which lists 265 pages with a title and
description each and covers both apps. For every complaint type it decides whether
the docs already cover the problem.

### The definition of "buried" had to change

The plan was to treat pages buried deep in the documentation tree as hard to find.
Measuring the index killed that idea: 228 of the 265 pages sit at the same depth.
The tree is flat, so depth carries no information at all.

The replacement rule is better anyway, because the real question was never how deep
a page sits. It is whether the merchant would find it.

So each complaint type is judged with the merchants' own quotes placed next to the
doc index, and the test is: if a merchant typed the words in these reviews into a
search box, would these page titles come back?

- documented and easy to find: a page covers it in words merchants actually use
- documented but buried: a page covers it in internal or product vocabulary
- not documented: nothing covers it

This makes the finding actionable. When the answer is "buried", the fix is renaming
or cross-linking a page rather than writing one, so the tool also returns a
suggested title in the merchant's words.

### Results

| Tag | Complaint types | Reviews affected |
|---|---|---|
| Documented but buried | 4 | 58 |
| Documented and easy to find | 6 | 55 |
| Not documented | 2 | 20 |

The largest single complaint type, `feature_missing` with 32 reviews, is tagged
buried. So is `app_unreliable` with 18.

Two things are genuinely not documented anywhere. **How to contact support** has no
page at all: nothing explains how to reach a human, what response times to expect,
how to escalate, or what coverage looks like during peak season. Fourteen reviews
complain purely about support, and several of those specifically describe not
knowing how to reach anyone. **Unexpected order changes** also has no page, despite
six reviews describing products appearing on customer orders without consent.

### Known limitations of this stage

The judgement is made from titles and descriptions only, not from reading the 265
pages. A page whose description undersells its contents will be judged too harshly.
This was a deliberate trade: the description is also all a merchant sees in a search
result, so it is the right thing to judge findability on, but it is the wrong thing
to judge the writing on. This stage measures findability, not quality.

The tags are one model's judgement and have not been checked by hand the way the
review classifications will be.
