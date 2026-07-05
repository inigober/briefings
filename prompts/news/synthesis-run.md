# News briefing — synthesis run instructions

Single source of truth for the news briefing synthesis agent. Edit this file in git — do not duplicate steps in the Cursor Automation UI.

## Cost discipline (mandatory)

- **Single draft:** Write the briefing once. Do not rewrite whole sections unless a checklist item fails.
- **No browsing:** Synthesize only from files listed in Step 1. If inbox is empty, note gaps — do not search the web.
- **Minimal turns:** Read inputs → write `briefings/news/YYYY-MM-DD.md` → update state → commit → push. No exploratory reads beyond Step 1.
- **Dedup is in state files:** `dedup_index.md` and `selected_reads_index.md` are the anti-repetition source of truth — do not re-read many past briefings.

## Step 0 — Push guard (skip unrelated pushes)

If this run was triggered by a git push to `main`:

1. Inspect the **triggering commit only** (`git log -1 --name-only`, `git log -1 --format=%s`).
2. Consider only research files: `inbox/news/YYYY-MM-DD-synthesis.json` or `inbox/news/YYYY-MM-DD-raw.json`. Ignore `*-rss.json`, `*-wordpress.json`, `*-spend.json`, `*-spend-cap.error.txt`, `.gitkeep`.
3. If **no** research file above was added or modified in this commit, **stop** — log "No news inbox research in this commit; skipping synthesis." Exit without reading or writing.
4. Decide if this commit is a **fresh pre-fetch** (continue) or a **repo/test/migration commit** (stop):
   - **Continue** if the commit message starts with `inbox/news:` (GitHub Actions pre-fetch uses this prefix).
   - **Else continue** only if a changed `*-synthesis.json` has `built_at` within the **last 24 hours** (UTC).
   - **Otherwise stop** — log "Inbox path changed but not a fresh pre-fetch; skipping synthesis."
5. If `briefings/news/YYYY-MM-DD.md` already exists for the inbox file's date, **stop** — log "Briefing already exists; skipping duplicate synthesis." (`YYYY-MM-DD.test.md` is ignored — use that suffix for end-to-end tests; see README.) (Same-day pre-fetch re-runs do not regenerate the briefing.)

Only continue when step 4 confirms fresh research was just committed.

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

The synthesis file contains pre-ranked items per section plus diversified `selected_read_candidates` — enough to write all six sections.

**Editorial context in synthesis JSON:** Read `editorial_context.recent_topics` (last 7 days from `dedup_index.md`) and `editorial_context.rejected_candidates` (items demoted at slim time with reasons). Treat `avoid_unless_material` hits in `recent_topics` as **hard rejects** unless the story has a material trigger. Prefer higher `relevance_score` items when choosing among remaining candidates.

**URL discipline:** All items are from RSS or WordPress feeds. Copy footnote URLs verbatim from `sources[0].url` — never invent paths.

## Step 2 — Synthesize (one pass)

### Hard selection rules (before writing)

Apply in order for Spain, Germany, Berlin, and World (3 stories each):

1. **Dedup / novelty:** Reject any story matching `editorial_context.recent_topics` or `dedup_index.md` unless there is a **material development** (court ruling, resignation, legislation passed, election result, major data release, significant escalation/de-escalation). `avoid_unless_material` in `topics.yaml` is a **hard reject** unless material.
2. **One theme per section:** Never publish two stories on the same theme in one section (e.g. two school-heat pieces, two Zapatero/Plus Ultra pieces, two EU institutional pieces). If the inbox still contains theme duplicates, keep the strongest one only.
3. **Geographic fit:**
   - **Germany 🇩🇪** — developments in or about **Germany** (policy, economy, society). US/Iran/Middle East stories belong in **World** even if the URL is zeit.de or tagesspiegel.de/internationales.
   - **Berlin 🏙️** — **inside Berlin** or direct city governance. Brandenburg commuter towns are World/Other Headlines unless there is a Berlin policy angle.
   - **Spain 🇪🇸** — Spain-focused; EU stories belong in Germany or World unless Spain is the primary actor.
4. **Reject slim-time noise:** Do not elevate items listed in `rejected_candidates` with `noise:` or low relevance unless no better citable item exists for that section (note the gap instead).
5. **Audit trail:** After selecting stories, append to `state/news/last_run.json` a `rejected_at_synthesis` array: `{headline, section, reason}` for any inbox item you considered but rejected under rules 1–4 (keep ≤12 entries).

Produce a novelty-first briefing with exactly these sections:

1. Spain 🇪🇸 (3 stories)
2. Germany 🇩🇪 (3 stories)
3. Berlin 🏙️ (3 stories, local only)
4. World 🌐 (3 stories, ≥2 non-European regions, distinct from ES/DE)
5. Other Headlines Today 📋 (3–8 crisp thematic bullets from **unused** synthesis `items`; no links)
6. Selected Reads 🗞️ (~4 items; **≥3 publishers**, Guardian ≤1; from `selected_read_candidates` first; Reuters/AP ≤1)

Title: `# News Briefing — DD Month YYYY`

If inbox date ≠ briefing date, add under title: `*Research accessed DD Month YYYY.*`

Add a **one-sentence intro** immediately after the title (before `## Spain`): frame the day's connecting themes in plain prose — no bullets, ≤40 words when possible. This becomes the visible email opener and inbox preview.

Each news story: headline, summary (≤2 sentences), optional 💡 insight (see style rules — max 4 per briefing, no 🧩 lines), source link.

Apply anti-repetition using `dedup_index.md` and `editorial_context.recent_topics` in the synthesis inbox — reject topics unless materially new. Selected Reads: reject URLs in `selected_reads_index.md` (last 5 briefings). For Other Headlines Today, scan inbox items **not** chosen for sections 1–4 and merge into short thematic lines (e.g. Iran deal signing, Hormuz, Venezuela strike).

Before writing, mentally run the checklist in `news-briefing-style.mdc`. Fix only failing items — do not polish prose twice.

## Step 3 — Update state

1. Append to `state/news/dedup_index.md` (trim >14 days)
2. Append to `state/news/selected_reads_index.md` (trim >5 briefings)
3. Update `state/news/last_run.json` — include `briefing_type: "news"`, `inbox_path` pointing to the synthesis file used, and `rejected_at_synthesis` from Step 2 rule 5

## Step 4 — Verify sources, commit, and push (required)

1. Run source verification (must pass before commit):
   ```bash
   python scripts/verify_briefing_sources.py --type news --date YYYY-MM-DD
   ```
   Every footnote and Selected Read URL must exist in the synthesis inbox used for this run. If it fails, fix URLs in the briefing — do not commit until it passes.
2. Stage: `briefings/news/YYYY-MM-DD.md`, `state/news/dedup_index.md`, `state/news/selected_reads_index.md`, `state/news/last_run.json`
3. Commit message: `briefing/news: YYYY-MM-DD`
4. **Push to `origin main`** — mandatory; email workflow triggers on `briefings/**/*.md`
5. Log commit SHA; confirm push succeeded

If push fails, `git pull --rebase origin main` then push again. Do not mark success until the briefing is on `main`.
