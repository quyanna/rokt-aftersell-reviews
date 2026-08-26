# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Stage 1 of 5: download Shopify App Store review pages and save the raw HTML.

Why this is its own stage: parsing HTML is fiddly and the parser will have bugs.
Keeping the download separate means every bug fix is re-tested against files
already on disk instead of hitting Shopify's servers again.

Usage:
    uv run fetch.py                      # both Aftersell apps
    uv run fetch.py some-other-app       # any Shopify app slug

Re-running is free: pages already on disk are skipped without a request.
To refetch a page, delete its file. To refetch an app, delete its directory.
"""

import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SLUGS = ["aftersell", "upcart-cart-builder"]

# Identifies the script and gives Shopify a way to contact us if it is a problem.
USER_AGENT = (
    "aftersell-review-triage/1.0 "
    "(portfolio project; contact quyannacampbell@gmail.com)"
)

RAW_DIR = Path(__file__).parent / "data" / "raw"
SECONDS_BETWEEN_REQUESTS = 1.0
TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 4

# Each review sits in an element carrying this exact attribute. Chosen over CSS
# class names, which are generated Tailwind utilities and change without notice.
REVIEW_MARKER = 'data-merchant-review=""'

# Pagination links look like href=".../reviews?page=91". The highest number in
# the set is the last page.
PAGE_LINK = re.compile(r"reviews\?page=(\d+)")


def fetch(url):
    """GET a URL and return the page as text. Retries with growing waits."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")

        except urllib.error.HTTPError as error:
            # 404 means a bad slug and 403 means we are blocked. Neither improves
            # by asking again, so fail immediately instead of waiting 7 seconds
            # to deliver the same error. 429 (rate limited) does improve, so it
            # falls through to the retry below.
            if error.code == 404:
                raise RuntimeError(
                    f"404 Not Found: {url}\n"
                    f"Check the app slug - it is the part of the App Store URL "
                    f"after apps.shopify.com/, e.g. 'aftersell'."
                ) from None
            if 400 <= error.code < 500 and error.code != 429:
                raise RuntimeError(f"HTTP {error.code} on {url}") from None
            problem = f"HTTP {error.code}"

        except (urllib.error.URLError, TimeoutError) as error:
            problem = str(error)

        if attempt == MAX_ATTEMPTS - 1:
            raise RuntimeError(f"gave up on {url} after {MAX_ATTEMPTS} attempts: {problem}")

        wait = 2**attempt  # 1s, then 2s, then 4s
        print(f"      {problem} - retrying in {wait}s", file=sys.stderr)
        time.sleep(wait)


def last_page_number(html):
    """Read the highest page number out of a page's pagination links."""
    numbers = [int(n) for n in PAGE_LINK.findall(html)]
    if not numbers:
        raise RuntimeError(
            "no pagination links found - the page layout may have changed, "
            "or this app has only one page of reviews"
        )
    return max(numbers)


def save(path, html, label):
    """Write a page to disk, but only if it actually contains reviews."""
    count = html.count(REVIEW_MARKER)
    if count == 0:
        raise RuntimeError(
            f"{label} came back with 0 reviews in {len(html):,} bytes. "
            f"Refusing to save it - an empty page silently becomes a hole in the "
            f"dataset. Open the URL in a browser and check whether the markup changed."
        )
    path.write_text(html, encoding="utf-8")
    return count


def fetch_app(slug):
    """Download every review page for one app slug."""
    out_dir = RAW_DIR / slug
    print(f"\n{slug}")

    # Page 1 does double duty: it is data, and it tells us how many pages exist.
    page_one_path = out_dir / "page-001.html"
    had_page_one = page_one_path.exists()

    if had_page_one:
        page_one_html = page_one_path.read_text(encoding="utf-8")
    else:
        # Fetch before mkdir, so a bad slug does not leave an empty directory.
        page_one_html = fetch(f"https://apps.shopify.com/{slug}/reviews?page=1")
        out_dir.mkdir(parents=True, exist_ok=True)
        save(page_one_path, page_one_html, f"{slug} page 1")
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    total_pages = last_page_number(page_one_html)
    print(f"  {total_pages} pages to collect")

    downloaded = 0 if had_page_one else 1
    cached = 1 if had_page_one else 0
    reviews = page_one_html.count(REVIEW_MARKER)

    for page in range(2, total_pages + 1):
        path = out_dir / f"page-{page:03d}.html"

        if path.exists():
            reviews += path.read_text(encoding="utf-8").count(REVIEW_MARKER)
            cached += 1
            continue

        label = f"{slug} page {page}"
        html = fetch(f"https://apps.shopify.com/{slug}/reviews?page={page}")
        reviews += save(path, html, label)
        downloaded += 1
        print(f"  page {page:3d}/{total_pages}  {len(html):>7,} bytes")
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    print(f"  done: {downloaded} downloaded, {cached} already on disk, "
          f"{reviews} reviews across {total_pages} pages")


if __name__ == "__main__":
    slugs = sys.argv[1:] or DEFAULT_SLUGS
    try:
        for slug in slugs:
            fetch_app(slug)
    except RuntimeError as problem:
        # A plain message beats a stack trace for anyone reading over your shoulder.
        print(f"\nStopped: {problem}", file=sys.stderr)
        sys.exit(1)
    print(f"\nRaw HTML saved under {RAW_DIR}")
