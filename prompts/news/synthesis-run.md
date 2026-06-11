# News briefing — synthesis run instructions

Single source of truth for the news briefing synthesis agent. Edit this file in git — do not duplicate steps in the Cursor Automation UI.

## Cost discipline (mandatory)

- **Single draft:** Write the briefing once. Do not rewrite whole sections unless a checklist item fails.
- **No browsing:** Synthesize only from files listed in Step 1. If inbox is empty, note gaps — do not search the web.
- **Minimal turns:** Read inputs → write `briefings/news/YYYY-MM-DD.md` → update state → commit → push. No exploratory reads beyond Step 1.
- **Dedup is in state files:** `dedup_index.md` and `selected_reads_index.md` are the anti-repetition source of truth — do not re-read many past briefings.

## Step 0 — Push guard (skip unrelated pushes)

If this run was triggered by a git push to `main`:

1. Inspect which files changed in the triggering push.
2. If **no** file under `inbox/news/` was added or modified, **stop immediately** — log "No news inbox changes; skipping synthesis." and exit. Do not read files, write briefings, or commit.
3. If `briefings/news/YYYY-MM-DD.md` already exists for today's UTC date **and** inbox was not updated in this push, stop.

Only continue when fresh news inbox research was just committed.

## Step 1 — Read context (minimal set)

Read **only** these files, in order:

1. `.cursor/rules/news-briefing-style.mdc` — editorial rules and checklist
2. `config/briefings/news/topics.yaml` — section limits and `avoid_unless_material` lists
3. `state/news/dedup_index.md` and `state/news/selected_reads_index.md` — anti-repetition memory
4. The **3 most recent** `briefings/news/*.md` files — tone reference only (not for dedup; use state files for that)
5. `inbox/news/YYYY-MM-DD-synthesis.json` — **primary research input** (prefer today's UTC date)
   - If missing, fall back to `inbox/news/YYYY-MM-DD-raw.json` and log a warning
   - If today's file is missing, use the most recent `inbox/news/*-synthesis.json` (or `*-raw.json`) and flag `*Research accessed DD Month YYYY.*` in the briefing

**Do not read:** `inbox/news/*-rss.json` (already merged into raw), full `*-raw.json` when `*-synthesis.json` exists, or `config/briefings/news/sources.yaml` unless a section is genuinely thin after selection.

The synthesis file contains pre-ranked items per section plus `selected_read_candidates` — enough to write all six sections.

## Step 2 — Synthesize (one pass)

Produce a novelty-first briefing with exactly these sections:

1. Spain 🇪🇸 (3 stories)
2. Germany 🇩🇪 (3 stories)
3. Berlin 🏙️ (3 stories, local only)
4. World 🌐 (3 stories, ≥2 non-European regions, distinct from ES/DE)
5. What Matters Today 🧠 (3–4 themes, not recaps)
6. Selected Reads 🗞️ (~4 items from `selected_read_candidates` or inbox items; Reuters/AP ≤1)

Title: `# News Briefing — DD Month YYYY`

If inbox date ≠ briefing date, add under title: `*Research accessed DD Month YYYY.*`

Each news story: headline, summary, 💡 insight, 🧩 broader context, source link.

Apply anti-repetition using `dedup_index.md` — reject topics unless materially new. Selected Reads: reject URLs in `selected_reads_index.md` (last 5 briefings).

Before writing, mentally run the checklist in `news-briefing-style.mdc`. Fix only failing items — do not polish prose twice.

## Step 3 — Update state

1. Append to `state/news/dedup_index.md` (trim >14 days)
2. Append to `state/news/selected_reads_index.md` (trim >5 briefings)
3. Update `state/news/last_run.json` — include `briefing_type: "news"`, `inbox_path` pointing to the synthesis file used

## Step 4 — Commit and push to GitHub main branch (required)

1. Stage: `briefings/news/YYYY-MM-DD.md`, `state/news/dedup_index.md`, `state/news/selected_reads_index.md`, `state/news/last_run.json`
2. Commit message: `briefing/news: YYYY-MM-DD`
3. **Push to `origin main`** — mandatory; email workflow triggers on `briefings/**/*.md`
4. Log commit SHA; confirm push succeeded

If push fails, `git pull --rebase origin main` then push again. Do not mark success until the briefing is on `main`.
