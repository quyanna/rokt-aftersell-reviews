# Using brief.css

Hand this file and `brief.css` to Claude Code together. It's the stylesheet from the two
Rokt prep documents.

## Page skeleton

```html
<body>
<div class="wrap">
  <header class="mast">
    <p class="eyebrow">Small label above the title</p>
    <h1>Title with <em>one word</em> in magenta</h1>
    <p class="standfirst">One or two sentences saying what this document is for.</p>
    <div class="mast-meta">
      <span class="chip"><b>Label</b> value</span>
    </div>
  </header>

  <section>
    <div class="sec-head"><span class="sec-num">01</span><h2>Section title</h2></div>
    <div class="sec-body">
      <p class="lede">Opening sentence, slightly larger.</p>
      <p>Body text.</p>
    </div>
  </section>

  <footer>…</footer>
</div>
</body>
```

Everything inside a section goes in `.sec-body` — that's what indents content under the
number on wide screens.

## The colour rule

Three accents, each with a fixed meaning. Never pick one because it looks nice.

| Colour | Variable | Means |
|---|---|---|
| Magenta | `--mag` | the subject, the key point, "this is the thing" |
| Teal | `--teal` | a strength, evidence, something going well |
| Amber | `--amber` | a gap, a risk, a caveat |

## Components

**Cards** — `.card` plain, `.card.good` teal, `.card.warn` amber, `.card.key` magenta.
Each takes an optional `<p class="card-label">SMALL LABEL</p>` as its first child.

**Pull quote** — `.say` for a single line you'd actually say out loud. `.say-long` with
`<p>` children inside for a multi-paragraph script.

**Stat blocks** — `.grid3` containing `.stat` divs, each holding `<span class="n">` (the
number), `<span class="l">` (the label), `<span class="s">` (a sub-line).

**Rated bars** — `.bar-row` with `.bar-name`, `.bar-track > .bar-fill`, `.bar-val`, and an
optional `.bar-note` for the explanation underneath. Add `.s` to the fill for teal, `.g`
for amber.

**Timeline** — `.tl` wrapping `.tl-item` blocks (`.tl-yr`, `.tl-t`, `.tl-d`). Add `.hi` to
an item to mark it as important.

**Q&A** — `.qblock` with `.qtxt` (the question), `.qmeta` (what it's testing), then either
`.say-long` for a script or `.a` for commentary. `.aside` for a note underneath.

**Tables** — plain `<table>`, already styled. Good for anything with two or three columns.

**Figures** — `<figure><div class="svg-card">…svg…</div><figcaption>…</figcaption></figure>`

## Charts

Hand-written inline SVG, no chart library. Keep to a `viewBox` around `0 0 880 300` so it
scales with the column. Rules that keep them readable:

- One consistent scale per chart. Work out pixels-per-unit once and use it for every bar.
- Label values directly on the bars. No separate legend if you can avoid it.
- Check text fits inside its box — roughly 6px per character at 13px Newsreader, 9px at
  17px Bricolage, 6.6px at 11px JetBrains Mono.
- Put the honest caveat in the `figcaption`, not buried elsewhere.

## Voice

The writing matters as much as the CSS. What makes these documents work:

- Say the uncomfortable thing plainly rather than softening it
- Numbers instead of adjectives — "4 of 10 negative reviews" not "many reviews"
- Flag where sources disagree instead of picking one and sounding confident
- Every section should change what the reader does, not just inform them
- Short sentences. No corporate vocabulary.
