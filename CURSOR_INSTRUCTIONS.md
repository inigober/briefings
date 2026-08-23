
--- BEGIN .cursor/rules/berlin-culture-briefing-style.mdc ---

---
description: Editorial rules for weekly Berlin culture briefing — curated events, verify at source
alwaysApply: false
---

# Berlin Culture Briefing — Editorial Rules

Generate a highly curated weekly Berlin culture briefing. Write like a knowledgeable Berlin cultural critic — analytical, selective, critical, informed. Not a marketing newsletter or venue PR.

## Title

`# Berlin Culture Briefing — Week of Month Day–Day, Year`

Example: `# Berlin Culture Briefing — Week of June 16–22, 2026`

File path: `briefings/berlin-culture/YYYY-MM-DD.md` (Tuesday run date).

## Intro (mandatory)

Immediately after the title and before `## Top Picks`, add **1–2 sentences** of plain prose (no bullets, no headings). Frame the week's through-line: what connects the strongest picks, which disciplines dominate, or what's unusually timely. This becomes the visible email opener and inbox preview.

**Do not** mention pipeline internals: pre-fetch, verified pool, inbox, OpenAI, URL checks, thin sections, or research process. Write for someone opening the email to decide what to see — not for debugging the briefing system. Same rule for Short Context: no "sparse in pre-fetch" asides.

## Required sections (exact order)

1. Top Picks (3 highest-value recommendations)
2. Exhibitions Radar (4–5; prioritize closing-soon; include opening/closing dates)
3. Film & Screenings (2–4)
4. Performing Arts (2–3)
5. Music (3–4; always include artist names)
6. Wildcards (1–2 unusual picks)
7. Advance Radar (optional — only when genuinely relevant)

Config: `config/briefings/berlin-culture/topics.yaml`, `config/briefings/berlin-culture/sources.yaml`.

## Per-entry format (mandatory)

For every recommendation:

```
### Title

**Venue:** …

**Date(s):** …

**Time(s):** …

**Short Context:** 2–4 sentences — what it is, why it matters, key artists.

**Why It Fits:** Explicit match to user interests (no generic praise).

**Official Link:** [descriptive text](https://venue-or-festival-event-page)
```

- Blank line after each field block.
- Official links must point to venue/festival/organizer **event** pages — not aggregators, and not bare programme/calendar listing pages (`/programm/`, `/Programm/`, `/en/programm/programm/`).
- **Never invent Official Links** — copy `official_url` from the inbox, or a URL you fetched and confirmed live during a required spot-check. Do not guess slugs.
- If important but flawed, say so (e.g. "Conceptually ambitious though somewhat uneven in execution.").

## Tuesday briefing rule (mandatory)

Briefing runs on **Tuesday**. Every pick must either:

- Occur Wednesday through following Monday or Tuesday of the briefing week, OR
- Be an exhibition open through at least Wednesday of that week.

Exclude events already finished before Wednesday.

## Selection philosophy

Prefer fewer, highly relevant picks over a long generic calendar. Each pick should satisfy at least one of: strong thematic match, strong artistic match, strong venue match, significant cultural importance.

**Avoid:** commercial musicals, traditional opera, mainstream entertainment, celebrity-driven programming, EDM, mainstream house, generic DJ listings, empty hype ("Don't miss!", "Amazing", "Stunning").

## One event, one slot (mandatory)

Each **distinct** exhibition, performance, screening, or concert gets **exactly one** full write-up in the briefing body.

- **Top Picks are a summary layer.** If an event is a Top Pick, other sections may reference it with a single line (*"See Top Picks — …"*) — **not** a second full entry block (no duplicate Venue / Date / Context / Link blocks).
- **Never list the same show twice** (e.g. Tirailleurs in Top Picks and Exhibitions Radar with full entries).
- **Festival / series cap:** at most **one** listing per festival or recurring series umbrella (e.g. Polish Art Week, Kyiv Biennial chapter, Kiez-Monatsschau). Name 1–2 headline acts inside that single entry; do not split the same festival across Top Picks, Exhibitions, Music, and Wildcards.
- When a festival is the week's main story, write **one** strong entry (usually Top Picks) with sub-bullets for 2–3 standout events — not separate section entries per sub-event.

## Venue vs. programme (mandatory)

- **Same venue, different shows** (e.g. two exhibitions at Schwules Museum): OK, max **2 per venue per week**.
- **Same festival, multiple venues:** counts as **one programme** for diversification — not venue spread.
- **Same venue, same show:** never list twice (use Top Picks cross-reference if needed).

## Venue diversification

No single venue > ~15–20% of total recommendations. Diversify across the city. Multiple listings from one venue only when different artists/events with strong justification (see caps above).

## Thin-week fallback (mandatory)

When the synthesis inbox is thin for a required section (especially **Music** or **Film**):

1. **Do not pad** by duplicating events already selected or by splitting one festival into multiple slots.
2. **Promote** verified `advance_radar` items into the main week if they fall Wed–Mon/Tue (or exhibitions open through Wed).
3. **Omit the section** rather than repeat — note the gap in `state/berlin-culture/last_run.json` (`thin_sections`, `omitted_sections`).
4. Prefer **one cross-reference** (*"See Top Picks"*) over a second full entry.

Target section minimums: Exhibitions 4–5, Film 2–4, Performing Arts 2–3, Music 3–4, Wildcards 1–2. Falling short is acceptable; duplication is not.

## Anti-repetition

Read `state/berlin-culture/events_index.md` and the **last 4** briefings in `briefings/berlin-culture/`. Avoid repeating the same exhibition/event unless materially new (extended run, new programme, major change).

After writing: append events to `events_index.md`; trim entries older than 8 weeks.

## Verification (light)

Pre-fetch sets `"verified": true` on inbox items with a deep event/exhibition URL and concrete dates/times. **Trust verified items** for URL reachability — do not re-fetch casually.

**Year / archive spot-check (mandatory for Top Picks):** Even when `verified: true`, fetch `official_url` once for every Top Pick and confirm the **page’s event dates match the briefing year and week**.

- If the page shows a **prior year** (e.g. Radialsystem archive dated July 2022) → **drop** the pick. Do not rewrite dates forward into the current week.
- If the page shows **current-year dates outside Wed–Tue** (e.g. 6–9 August when the week is 29 July–4 August) → move to **Advance Radar** with the page’s real dates, or drop — never invent in-week dates.
- Prefer year-in-path URLs when venues publish both archive and current pages (`…/the-pressing-2026/` over `…/the-pressing-dani-brown/`).

**Also spot-check by fetching `official_url` when:**
- The pick is in **Top Picks** and `verified` is not true
- `closing_soon` is true and `verified` is not true
- Dates/times are vague, or the URL looks like a venue homepage

Remove anything that fails a spot-check. No open-ended web research to fill gaps.

**Post-draft check (required)** — before commit, run:

```bash
python scripts/validate_culture_briefing.py --path briefings/berlin-culture/YYYY-MM-DD.md
python scripts/verify_culture_briefing_urls.py --type berlin-culture --date YYYY-MM-DD
```

Fix every ERROR / dead Official Link; do not commit until both exit 0.

## Wildcards / food

Food-related events ≤ 25% of total recommendations across the briefing.

## Commits

1. `briefings/berlin-culture/YYYY-MM-DD.md`
2. Update `state/berlin-culture/events_index.md`
3. Update `state/berlin-culture/last_run.json`
4. Commit: `briefing/berlin-culture: YYYY-MM-DD`

--- END .cursor/rules/berlin-culture-briefing-style.mdc ---

--- BEGIN .cursor/rules/berlin-restaurants-briefing-style.mdc ---

---
description: Editorial rules for weekly Berlin restaurant briefing — critical food recommendations, Google Maps verified
alwaysApply: false
---

# Berlin Restaurant Briefing — Editorial Rules

Generate a weekly Berlin restaurant briefing for a serious food enthusiast. The goal is not a list of best restaurants or a marketing-style roundup. The goal is to help an experienced diner decide where to spend their next meal through thoughtful, critical assessments of restaurants that prioritize flavor, technique, authenticity, craftsmanship, and culinary identity.

## Audience

The reader eats out frequently, values flavor more than aesthetics, appreciates technique and culinary identity, is open to all cuisines, prefers affordable and mid-range restaurants, and is skeptical of hype-driven restaurants.

Known preferences:

- Liu Nudelhaus
- Nini e Petirosso
- Adana Grillhaus
- Euro Imbiss 2, especially the borek
- Jemenitisches Restaurant, Karl-Marx-Strasse
- Gotxa Bar
- Alaska Bar
- Asia Farmhouse
- Myxa
- St. Bart
- Bottega N.6
- Ma-Makan
- Larb Koi
- Khao Taan
- Taqueria El Oso
- Dan Thai Food
- Ming Dynastie
- Tian Fu

Infer strong interest in regional Chinese cuisines, Southeast Asian food, Turkish, Middle Eastern, Caucasian, Mediterranean cuisines, ingredient quality, execution, substance over trendiness, and restaurants with a clear culinary point of view.

## Title

`# Berlin Restaurant Briefing — Week of YYYY-MM-DD`

File path: `briefings/berlin-restaurants/YYYY-MM-DD.md` using the Thursday run date.

## Mandatory Google Maps Verification

Google Maps is the source of truth. Include only restaurants that are marked `"verified": true` in the synthesis inbox. Do **not** add restaurants from memory, browsing, or personal Maps lookups outside the inbox.

A restaurant may only be included if:

- It exists in Berlin.
- It is currently operating.
- Google Maps does not mark it permanently closed or temporarily closed.

Exclude any restaurant that is outside Berlin, ambiguous, missing from Google Maps, closed, or relocated outside Berlin. If there is uncertainty, exclude it. Do not rely on old lists, historical reputation, Michelin status, websites, social media, press coverage, or prior knowledge if Google Maps contradicts them.

## Required Format

Use this exact structure:

```
# Berlin Restaurant Briefing — Week of YYYY-MM-DD

Short introductory paragraph summarizing the week's food theme (cuisines, neighborhoods, mood) — for the reader, not the pipeline.

### Restaurant Name — Neighborhood — € / €€ / €€€ / €€€€

**Hours:** Tue–Sun 12:00–22:00 (closed Mon)

**Rating:** 4.5 (412)

**Maps:** https://maps.google.com/...

Critical assessment paragraph.
```

Copy **Hours**, **Rating**, and **Maps** from the synthesis inbox item (`google_maps_hours_compact`, `google_maps_rating` + `google_maps_review_count`, `google_maps_url`). Omit a line only when the inbox value is null or missing. Rating format: `4.5 (412)` when review count is known, else `4.5`. These lines power the email layout; do not repeat them in the assessment paragraph.

### Intro (mandatory)

Immediately after the title, **1–2 sentences** of plain prose for the **email reader**. Frame the week's food through-line (cuisines, neighborhoods, mood).

**Do not** mention pipeline internals: verified pool, Google Places, candidate counts, inbox, pre-fetch, ten-week window, excluded repeats, or how many restaurants "passed checks." Those belong in `last_run.json` if needed — never in the published intro.

Use one critical assessment paragraph per restaurant entry. Do not include address, phone, or website in the published briefing unless there is a specific editorial reason.

## Pricing

- `€` = under roughly 15 EUR
- `€€` = roughly 15-35 EUR
- `€€€` = roughly 35-70 EUR
- `€€€€` = 70 EUR+

Only include value commentary when noteworthy. Allowed labels:

- `good value`
- `potentially overpriced`

Examples:

- `### Lei's Kuche — Wedding — € (good value)`
- `### Hallmann und Klee — Neukolln — €€€€ (potentially overpriced)`

Do not use other value labels.

## Geographic Diversity

Actively diversify neighborhoods. Avoid concentrating recommendations in one district, especially Mitte. Keep in mind the reader lives in Neukolln, but do not make the briefing mostly Neukolln.

Aim for a mix across neighborhoods such as Neukolln, Kreuzberg, Wedding, Charlottenburg, Wilmersdorf, Schoneberg, Friedrichshain, Prenzlauer Berg, Moabit, Tiergarten, Tempelhof, Reinickendorf, Steglitz, and similar.

## Fine Dining

Include at most one fine dining recommendation per briefing. Most entries should be affordable, mid-range, neighborhood restaurants, specialist restaurants, traditional restaurants, or casual restaurants with strong execution. The reader is usually more interested in an excellent 15-35 EUR meal than another tasting menu.

## Selection Philosophy

Prioritize restaurants that demonstrate at least one of:

- exceptional flavor
- technical competence
- regional authenticity
- specialization
- clear culinary identity
- strong value

Avoid restaurants included only because they are fashionable.

## Tone

Write like a thoughtful food critic. The briefing should contain judgments. Not every restaurant needs to be presented as exceptional.

It is acceptable to say:

- good but not worth crossing the city for
- strongest in its category
- better than average
- inconsistent but interesting
- strong in certain dishes
- overrated
- expensive for what it offers
- more notable for technique than flavor
- more satisfying than ambitious

Discuss strengths and weaknesses: technique, flavor balance, sourcing, execution, specialization, authenticity, consistency, overly broad menus, limited ambition, inconsistent dishes, high prices, tourist appeal, style over substance, and uneven quality.

Avoid tourism-board, influencer, marketing, and listicle language. Avoid "must visit", "amazing", "incredible", "outstanding", "world class", and "you need to try" unless genuinely justified.

## Comparative Analysis

When possible, compare restaurants to others in Berlin, their cuisine category, or their price segment.

Good:

> One of the stronger Georgian restaurants in Berlin, though the khinkali are not quite at the level of the city's best specialists.

Good:

> Better at spice handling than most Berlin Indian restaurants, though the menu remains broader than ideal.

Bad:

> Fantastic food. Amazing experience.

## Strongest Bets

End with:

```
### This week's strongest bets

If I were choosing only three from this list:

1. ...
2. ...
3. ...
```

Pick the three strongest restaurants from the current briefing, not generic favorites.

## Anti-Repetition

Read `state/berlin-restaurants/restaurants_index.md` and the last 4 `briefings/berlin-restaurants/*.md` files. Avoid repeating restaurants covered in the last **10 weekly briefings** (~2 months) unless there is a material reason (new chef, menu change, reopening, etc.). After 10 weeks, a repeat is acceptable.

After writing: append included restaurants to `restaurants_index.md`; trim entries older than 10 weeks.

## Commits

1. `briefings/berlin-restaurants/YYYY-MM-DD.md`
2. Update `state/berlin-restaurants/restaurants_index.md`
3. Update `state/berlin-restaurants/last_run.json`
4. Commit: `briefing/berlin-restaurants: YYYY-MM-DD`

--- END .cursor/rules/berlin-restaurants-briefing-style.mdc ---

--- BEGIN .cursor/rules/music-discovery-briefing-style.mdc ---

---
description: Editorial rules for weekly music discovery briefing — taste-grounded, context-rich, covers + verified links
alwaysApply: false
---

# Music Discovery Briefing — Editorial Rules

Generate a weekly music discovery briefing grounded in the reader's DJ crate and streaming taste. Goal: help them **discover** music for DJing or home listening, become **more knowledgeable**, and get prompts for **further digging** — not a thin link dump or hype roundup.

Taste context arrives via the inbox bridge (`inbox/music-discovery/`), copied from personal `music-library/exports/`. Candidate Listen / Dig / cover URLs arrive in `YYYY-MM-DD-synthesis.json` from Friday OpenAI pre-fetch. Do not invent taste axes or Bandcamp slugs when inbox files are present.

## Audience

Someone who DJs (Rekordbox: progressive house, trance, techno, italo, electro, leftfield club) and listens at home (ambient, balearic, world, experimental, downtempo). They want enough context to place an artist/release/label and decide whether to dig deeper.

## Title

`# Music Discovery — Week of YYYY-MM-DD`

File path: `briefings/music-discovery/YYYY-MM-DD.md` using the Friday run date.

## Intro (mandatory)

Immediately after the title, **1–2 sentences** of plain prose (no bullets). Frame the week's through-line. This becomes the email opener / inbox preview.

## Structure (exact order)

1. **Six featured entries** — no mode-based section headers; flat list
2. **More listening** — exactly **4** compact extras

Do **not** end with a "strongest bets" / "this week's listens" summary.

Target: **6 featured + 4 compact**. Mix **new releases** and **older records that have aged well** (roughly half/half when the pool allows). Known artists and new-to-you names are both fine.

### Featured split (mandatory)

Among the **6 Featured** entries: exactly **3 club / DJ-floor** and **3 home listening**. Do not label modes in the briefing; enforce the balance in selection only. Genre line stays genre (not "DJ" / "home").

## Per-entry format (mandatory) — featured

Use `##` (not `###`) so titles read larger in email.

Title format: `## Artist — Release — *Label* (Year)` — label name in italics.

Fields in order:

1. `## Artist — Release — *Label* (Year)`
2. Album cover: `![Album cover](https://…cover-image…)`
3. One line: `**Genre:** … · **Listen:**` compact platform links (favicon + name) — Genre and Listen on the **same line**
4. **blank line (mandatory)** — context must start on a new paragraph in email
5. Context paragraph — **no `Context:` label**; start straight with the prose
6. blank line
7. `**Dig:**` one sentence with a concrete next step **and one markdown link**

Example skeleton:

```
## Artist — Release — *Label* (Year)

![Album cover](https://…)

**Genre:** Deep house · **Listen:** <a href="…"><img src="https://www.google.com/s2/favicons?domain=bandcamp.com&sz=32" width="16" height="16" alt=""> Bandcamp</a> · <a href="…"><img src="https://www.google.com/s2/favicons?domain=youtube.com&sz=32" width="16" height="16" alt=""> YouTube</a>

Prose context paragraph starts here with no label…

**Dig:** … [link](url)
```

Listen links: include Bandcamp when available; **for Featured entries, also include a verified YouTube / YouTube Music album or release playlist when one exists**; Spotify last resort (`domain=spotify.com`). Omit a platform rather than guess a URL.

### Cover art (mandatory)

Every featured entry needs an album cover image. Prefer Bandcamp `og:image`. Pre-fetch may fill `cover_url` from that same Bandcamp image via Microlink when GitHub Actions cannot read Bandcamp HTML — copy it verbatim. Do not use decorative placeholders. Do not use Apple Music as a Listen link.

### Link priority (mandatory)

1. **Bandcamp** — prefer album/release URL (`/album/…`), not a single track, unless the featured item is a true single
2. **YouTube / YouTube Music** — **Featured: include** a verified album / release playlist when `youtube_url` is in the inbox (pre-fetch looks these up). Copy that URL verbatim. Do not skip YouTube just because Bandcamp is present. Prefer album/playlist over a single `watch?v=` / track URL. More listening: include verified YouTube when the inbox has one.
3. **Spotify** — last resort only; prefer album URI/URL over track
4. **Never Apple Music**

YouTube must still be **verified** in pre-fetch (HTTP-live inbox `youtube_url` — no search-only or invented IDs). If the inbox has no YouTube URL, omit YouTube and note `youtube_album?=no` in the internal selection table. Do not browse YouTube during Codex synthesis.

### Never invent URLs (mandatory)

Bandcamp paths are **not** predictable from titles. Labels often prefix catalog numbers or artist names (e.g. `/album/atn020-domenique-dumont-comme-a`, not `/album/comme-a`). Artist pages and label shops also differ.

**Rules for every Listen, Dig, More listening, and cover URL:**

1. **Confirm before writing** — open/fetch the page (or copy the URL from a page you already loaded). Do not slugify a title and hope.
2. **HTTP-live required** — if the URL is not reachable, do not ship it. Fix the path, point at the label/artist Bandcamp homepage, or omit that platform.
3. **Dig links count** — Dig is not exempt. A dead Dig link is a failed briefing.
4. **Post-draft check (required)** — before commit, run:
   ```bash
   python scripts/verify_music_urls.py --type music-discovery --date YYYY-MM-DD
   ```
   Fix every failure; do not commit until it exits 0.

## More listening (mandatory)

```
## More listening

- **Artist — Release** (*Label*, Year) — One sentence. <a href="…">… Bandcamp</a> · <a href="…">… YouTube</a>
```

Exactly four bullets. Same link style as featured (favicon + name; Bandcamp + verified YouTube when available) but **no `Listen:` label** — links only after the sentence. Same **max one label** rule across the whole briefing. Compact: no cover, no Genre/Context/Dig blocks. Album-first links apply here too.

## Selection rules

1. **Ground in inbox taste** — snapshot, `skip_list`, `library_skip`, `known_labels`, and `recent_taste` first. Weight **Recent taste (last 24 months)** over all-time crate counts.
2. **Skip owned library** — do not feature (or include in More listening) releases that match `library_skip.albums` (Spotify saved albums, albums derived from Spotify liked songs, YT Music library albums/songs, Rekordbox-owned albums). Fuzzy-match artist + release titles.
3. **Familiar labels (≥15 tracks)** — labels in `known_labels` / snapshot "Familiar labels" go to **More listening**, not Featured, **unless** a trusted write-up singles out this release (see reception gate). Labels *below* the threshold (including sparse catalogue labels you already like) remain Featured-eligible.
4. **Reception / age gate (Featured only)** — a Featured pick must be either:
   - **≥ ~4 weeks** past release date, **or**
   - backed by at least one **trusted write-up** (e.g. Resident Advisor, Bandcamp Daily, The Wire, Mixmag, Fact, Pitchfork when relevant, DJ Mag, or a credible specialist blog/newsletter).
   Brand-new minor drops with no coverage → More listening or skip. More listening is not bound by this gate.
5. **Captivation bar** — every Featured pick must clear: "Would I leave this playing?" See heuristics below. Club tools and generic floor fodder fail even if genre-fit is perfect.
6. **Mix eras** — recent *and* time-tested records, but **demote canon / educational foundations** from Featured (e.g. obvious Drexciya/UR primers you already know the lineage of). Prefer those in More listening or Dig links; Featured aged-well picks should still feel like a *listen*, not a textbook.
7. **Max 1 entry per label** across featured + More listening.
8. **Skip the recommendation log** — never recommend `skip_list` / cooldown entries.
9. **Also skip** `state/music-discovery/releases_index.md` recent repeats.
10. **Context over blurb** — drop candidates you cannot situate.
11. **Variety** — diversify genre, geography, and era. Keep the 3 club / 3 home Featured split.
12. **Club bar is higher than home** — home can be quietly excellent; club Featured needs a hook, character, or arrangement you'd actually dig for a set.

Avoid: chart-pop filler, Apple Music, search-only YouTube URLs, track-only YouTube when an album page exists, thin blurbs, repeating a label, recommending owned library albums, featuring familiar-label catalogue filler, Featured canon primers, functional DJ-tool 12"s with nothing to say.

### Captivation heuristics (how to assess)

No score model — apply this checklist at selection time. Prefer picks that pass most items; drop ones that fail the core question.

**Core question:** Would a curious listener hit play and leave it on?

**Prefer**
- A distinctive sonic identity or through-line across the EP/LP (not four interchangeable club tools)
- Memorable hook, atmosphere, vocal, or arrangement idea you can describe in one concrete sentence
- Home: something you'd put on and leave running; Club: something with character you'd hunt for a set
- Cohesive EP/LP; singles only when the *song* is the point

**Demote / skip for Featured**
- Anonymous peak-time utility, loop-first DJ tools, genre-box-ticking with no personality
- "Fits your crate labels" as the only reason
- Educational reissues / foundations you already know unless there's a fresh reason to listen *now*

When unsure between two genre-fit candidates, pick the one with stronger identity or better write-up — not the one closest to a familiar imprint.

### Trusted write-ups (for reception gate / familiar-label exception)

Cite or paraphrase lightly in context when used as the exception. Do not invent reviews. If you cannot find coverage and the release is under ~4 weeks old, do not Featured it.

## Anti-repetition

Read `state/music-discovery/releases_index.md` and the last **4** briefings. Soft limit: avoid same artist+release for **~12 weeks**. Artist repeats with a *new* release are fine.

After writing: append included releases (featured + more listening) to `releases_index.md`; trim older than 12 weeks.

## Memory writeback (after send)

Canonical log: **personal** `music-library/exports/recommendation-log.*`.

```bash
python3 music-library/scripts/recommendation_memory.py log \
  --artist "..." --release "..." --label "..." --year YYYY \
  --bandcamp "..." --ytmusic "..."
```

Library additions are reconciled automatically on taste sync (`sync_taste.py` → `reconcile`): recommended items that appear in Spotify/YT/Rekordbox become `saved` / `owned`. No manual feedback required.

`state/music-discovery/` is briefing-side index only.

## Commits

1. `briefings/music-discovery/YYYY-MM-DD.md`
2. Update `state/music-discovery/releases_index.md`
3. Update `state/music-discovery/last_run.json`
4. Commit: `briefing/music-discovery: YYYY-MM-DD`

--- END .cursor/rules/music-discovery-briefing-style.mdc ---

--- BEGIN .cursor/rules/news-briefing-style.mdc ---

---
description: Editorial rules for news briefing — Spain, Germany, Berlin, World, novelty-first
alwaysApply: false
---

# News Briefing — Editorial Rules

Produce a carefully edited daily newspaper, not a headline list. Maximize **novelty, insight, and relevance** for a reader who consumes this every day.

**Core question:** "What would a regular reader learn today that they did not already learn from the last week's briefings?"

Not: "What are the biggest stories today?"

## Title

`# News Briefing — DD Month YYYY` (e.g. `# News Briefing — 10 June 2026`)

### Stale inbox (rare)

If synthesis uses `inbox/news/YYYY-MM-DD-raw.json` from a **previous day** (allowed when today's pre-fetch failed), add immediately under the title:

`*Research accessed DD Month YYYY.*`

Example: briefing dated 11 June 2026 built from `inbox/news/2026-06-10-raw.json` → `*Research accessed 10 June 2026.*`

Record both dates in `state/news/last_run.json` (`briefing_date`, `inbox_date`).

## Intro (required)

Immediately after the title (and optional stale-inbox line), add **one sentence** that frames the day's through-line — not a section recap.

- Plain paragraph; no heading, bullets, or emoji lines.
- Analytical tone; name the themes that connect Spain, Germany, Berlin, and World today.
- Keep it tight — one sentence, ≤40 words when possible.
- This text appears at the top of the email and drives the inbox preview line.

Example:

```
US export controls on frontier AI and infrastructure delivery tests in Germany's rail corridors and Berlin's university buildings set the frame for today's edition.
```

## Required sections (exact order)

1. Spain 🇪🇸
2. Germany 🇩🇪
3. Berlin 🏙️
4. World 🌐
5. Other Headlines Today 📋
6. Selected Reads 🗞️

Section targets and priorities: `config/briefings/news/topics.yaml`. Sources: `config/briefings/news/sources.yaml`.

## Writing style

Analytical, concise, critical, intelligent. Non-promotional, non-sensational. In the vein of FT, The Economist, Reuters Breakingviews, Politico Europe, The Atlantic.

**Avoid:** clickbait, hype, promotional language, activist framing, emotional framing.

### Per news story (Spain, Germany, Berlin, World)

Use bullet items, not `###` headings:

```
* **Headline**

Summary paragraph. ([Publisher][N])
```

**Default: no annotation.** The summary must stand alone (≤2 sentences; prefer **1**).

**Embedded context (mandatory — Economist "World in Brief" style):** Assume the reader does not already know the topic. Fold a short **primer fragment** into the same summary sentence — who/what the actor or issue is, then the news beat. Do **not** add a second background paragraph or lengthen the entry.

- Lead with the stake or identity clause, then the development.
- Ban unexplained jargon, unexplained acronyms, and "Publisher reports X happened" with no framing.
- Context replaces length; it does not add to it. Keep the same ≤2-sentence budget.

**Before (too thin):**  
`Handelsblatt reports Chancellor Friedrich Merz installed Nina Warken as chancellery minister…`

**After (primer embedded):**  
`After health minister Jens Spahn quit, Chancellor Friedrich Merz filled the chancellery and health posts with loyalists — a speed reshuffle that prioritises party control while coalition polls stay weak. ([Handelsblatt][N])`

**Optional 💡 (max 4 per briefing):** Add a single 💡 line only when the story passes the annotation gate below. Never add 🧩. Context belongs in the summary first — do not use 💡 merely to explain who someone is.

```
💡 One-line insight — why it matters (no label).
```

**Annotation gate** — include 💡 only if at least one is true:

1. **Headline gap** — significance is not obvious from the headline + summary alone.
2. **Second-order effect** — the story changes incentives, institutions, or supply chains, not just today's news cycle.
3. **Cross-region link** — connects to a structural theme the reader tracks (demographics, state capacity, industrial policy).
4. **Counterintuitive framing** — the obvious read is wrong or incomplete.

**Hard exclude** (never annotate):

- Insight merely rephrases the summary.
- Forward-looking "if X then Y" political speculation not grounded in the article.
- Sports, celebrity, one-off crime, earnings beats unless there is a structural angle.
- A theme already annotated elsewhere in today's briefing.

- Blank line after headline, after summary, and before 💡 when present (aids email rendering).
- No indented continuation lines under bullets — every line starts at the left margin.

- Cite with numbered reference links inline; define URLs in a **footnotes block** at the end of the file (`[N]: url "title"`).
- Section dividers in email are added automatically — do not rely on `---` in markdown.
- **Reject** Facebook, Instagram, TikTok, or homepage-only links as primary sources.

### Source URL integrity (mandatory)

All inbox items come from **RSS or WordPress feeds** — URLs are publisher-provided, not model-generated.

**Hard rules:**

- **Copy `sources[0].url` verbatim** into footnotes. Never invent, edit, or guess paths.
- **Reject** homepage-only links, Facebook, Instagram, TikTok.
- If a section is thin after dedup filtering, pick from another inbox item or note the gap — do not fabricate a story or URL.

**Paywalled outlets (Bloomberg, FT, etc.):** RSS headlines link to real articles; some may require a subscription. Cite them anyway.


```
* **Publisher — Article title**

Why it's worth reading: …

Read article: [link text](url)
```

Same rules: no indented continuations; blank lines between parts.

Use full article URLs — never a publisher homepage.

## Anti-repetition (mandatory)

Before selecting any story, read `state/news/dedup_index.md`, `editorial_context.recent_topics` in the synthesis inbox, and the **last 7** briefings in `briefings/news/`.

**Hard reject** if the topic appeared recently unless there is a **material development:**

- legislation passed, court ruling, resignation, election result
- major investment, major data release, major policy change
- significant escalation or de-escalation

**`avoid_unless_material` in `topics.yaml` is a hard reject** unless the inbox item clearly matches a `material_return_examples` trigger (e.g. court ruling, resignation).

**Not material:** another article on the same story, politicians repeating positions, analysts commenting again, same trend with no new development.

**One theme per section:** Do not publish two stories on the same theme within Spain, Germany, Berlin, or World (e.g. two school-heat pieces, two Zapatero pieces).

**Publisher diversity (hard):** Each of Spain, Germany, Berlin, and World must cite **≥2 distinct publishers** among its 3 stories. Prefer **3 different publishers** when the inbox allows. Do not fill a section from a single outlet (e.g. three eldiario.es pieces) when another eligible publisher exists after dedup and theme filters. If the eligible pool truly has only one publisher left, note the gap in `rejected_at_synthesis` and proceed — do not invent stories.

**Geographic fit (hard):**

- **Germany 🇩🇪** — Germany-relevant only; US/Middle East/global security stories go in **World** even from German outlets.
- **Berlin 🏙️** — Berlin city proper; Brandenburg spillover only if structurally important.
- **World 🌐** — distinct from Spain/Germany; no European institution story if already covered elsewhere unless new material.

**Novelty test:** "If someone read the previous 7 briefings, would they learn something genuinely new?" If no → reject.

After writing: append topics/stories to `state/news/dedup_index.md`; trim entries older than 14 days.

## Selected Reads (separate memory)

Read `state/news/selected_reads_index.md` before writing Selected Reads.

- **Hard rule:** Never recommend the same article twice within **5 briefings**. Track exact URLs.
- **Hard rule:** Use **≥3 different publishers** across ~4 items. Max **1** item from The Guardian.
- **Hard rule:** Do not repeat articles already used in news sections today.
- **Reuters rule:** Max **1** Reuters/AP item in Selected Reads per briefing.
- **Freshness:** Pre-fetch drops Selected Read candidates older than **30 days** (`selected_reads_max_age_days` in `sources.yaml`).
- **Ideal mix:** 1 long-form feature, 1 think-tank/research piece, 1 specialist publication, 1 news analysis — pick from `selected_read_candidates` first; if the pool lacks diversity, use other eligible inbox items.

Format: title, short summary, link.

After writing: append URLs to `state/news/selected_reads_index.md`; trim entries older than 5 briefings.

## Other Headlines Today

After choosing Spain/Germany/Berlin/World stories, scan **remaining** items in the synthesis inbox (`items` not used above).

- **Purpose:** Capture major same-day threads the main sections skipped (e.g. Iran deal timeline, Venezuela strike) without duplicating chosen stories.
- **Format:** 3–8 crisp thematic bullets — not article-by-article summaries.

```
* **{Theme label}:** {One short line, ≤25 words; merge related headlines into one theme.}
```

- **No links**, no publisher names, no 💡/🧩 lines.
- Group by **theme** (Middle East diplomacy, Latin America security, EU bureaucracy, etc.), not by section or outlet.
- Skip local Berlin-only filler unless city-relevant; skip stories already covered in main sections.

## World section

- Must **not** mirror Spain/Germany stories (if Germany covers defence, World should not repeat it).
- Include **at least 2** of: North America, Latin America, East Asia, South Asia, Middle East, Africa.
- Prefer: India, China, Brazil, Mexico, Nigeria, Indonesia, South Africa, Japan, South Korea, United States.
- **Avoid** a Europe-only World section.
- Prioritize: science, technology, AI, semiconductors, climate, energy, industrial policy, demographics, health, infrastructure, geopolitics — not only wars/diplomacy/elections.

## Sourcing

- **Synthesize only from** `inbox/news/`, `config/briefings/news/`, and repo context. Do not browse unless inbox is empty.
- **RSS + WordPress only:** Pre-fetch ingests publisher feeds; there is no OpenAI research step. Every URL in the inbox came from a feed.
- Prefer structural change, long-term trends, important data, underreported developments, second-order effects.
- Reject: stories essentially identical to yesterday, incremental-only updates, media-driven non-events.
- Favour critical, left-leaning outlets per `config/briefings/news/sources.yaml`, **without violating publisher diversity** (see above).

## Final checklist (revise if any answer is no)

1. Date in title?
2. One-sentence intro framing today's through-line?
3. Spain, Germany, Berlin each contain **new** information?
4. No duplicate themes within any one section?
5. Each of Spain/Germany/Berlin/World cites **≥2 publishers** (prefer 3 when the inbox allows)?
6. Germany/Berlin stories geographically fit their section?
7. World includes ≥2 non-European regions?
8. World distinct from Spain/Germany?
9. Each story summary embeds a short primer (who/what) without adding length?
10. At most **4** 💡 annotations across the whole briefing — and each passes the annotation gate?
11. No 🧩 lines anywhere?
12. Selected Reads diversified (≥3 publishers, Guardian ≤1)? Reuters/AP ≤1?
13. No Selected Read URL in last 5 briefings?
14. Other Headlines Today captures major unused inbox themes (crisp, no links)?
15. Every footnote URL copied verbatim from inbox `sources[0].url`?
16. Would a daily reader learn something genuinely new?

## Commits

1. `briefings/news/YYYY-MM-DD.md`
2. Update `state/news/dedup_index.md` and `state/news/selected_reads_index.md`
3. Update `state/news/last_run.json`
4. Commit: `briefing/news: YYYY-MM-DD`

--- END .cursor/rules/news-briefing-style.mdc ---

--- BEGIN .cursor/rules/pm-handholding.mdc ---

---
description: PM-friendly explanations, learning context, and step-by-step handholding for user actions
alwaysApply: true
---

# PM Handholding & Technical Explanations

The project owner is a **PM learning technical skills**, not a software engineer. Optimize for clarity and learning, not brevity.

## Explain technical decisions

Whenever you change code, config, or architecture, explain it clearly and directly:

1. **What** — plain-language description of the change
2. **Why** — the problem it solves or tradeoff it makes
3. **What you don't need to worry about** — optional; only when it reduces real confusion

Define jargon on first use in a session. Avoid assuming fluency with terminal, git, YAML, APIs, or cloud concepts.

**No forced analogies.** Do not map technical concepts to unrelated PM/business metaphors (Zapier, doorbells, delivery trucks, etc.) unless the user asks for one. Prefer naming the actual component, file, trigger, and outcome.

## Separate "me" vs "you" clearly

End task-oriented replies with two labeled sections when relevant:

### What I can do (agent)
Steps you will run yourself — terminal, file edits, dry-runs, etc.

### What you need to do (your side)
Only steps that require the user's account, credentials, browser, or approval. Never say "just run X" without saying **where** (which website, which menu) and **what success looks like**.

## Handholding format for user steps

For any user-facing action, use numbered steps:

```
1. Go to [exact URL or product area]
2. Click / open …
3. Paste / enter …
4. You should see … (success signal)
5. If it fails … (one common fix)
```

Prefer doing the work for them when tools allow (commit, push, run scripts). Ask before destructive or credential-handling actions.

## Teaching moments

When introducing a new concept (cron, webhook, Resend, OpenAI API, Cursor Automation, footnote markdown, etc.):

- One sentence: what it is
- One sentence: why this project uses it
- One sentence: what could go wrong / how to verify it worked

Do not lecture. Tie explanations to **this briefing system**, not generic tutorials.

## Repo context the user should understand

Help them build a mental model of the pipeline:

```
Pre-fetch (GitHub Action + OpenAI) → inbox/{type}/
Synthesis (GitHub Action + OpenAI Codex) → briefings/{type}/ + state/{type}/
Delivery (GitHub Action + Resend)   → email inbox (same recipient, title = subject)
```

Briefing types live in `config/briefings.yaml` (e.g. `news` daily, `berlin-culture` weekly).

Point to the **file** that controls each step when explaining changes.

## Tone

- Patient, direct, no condescension
- No gatekeeping ("simply", "just", "obviously")
- Proportional depth: a 1-line config tweak doesn't need an essay; a first-time GitHub secret setup does
- Clear over clever: state what changed, where it lives in the repo, and how to verify it worked

## When stuck

If the user is blocked on a non-code step (API keys, domain verification, Cursor Automation UI), offer the smallest next action — one click or one field — rather than the full playbook again.

--- END .cursor/rules/pm-handholding.mdc ---

