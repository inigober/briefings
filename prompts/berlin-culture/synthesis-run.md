# Berlin culture briefing — synthesis run instructions

Single source of truth for the weekly Berlin culture briefing synthesis agent.

## Cost discipline

- **Single draft** after selection (and light verification where required).
- **Trust pre-fetch:** Items with `"verified": true` in the synthesis inbox were URL-checked at pre-fetch — do not re-fetch unless a checklist item fails.
- **Light browse only:** Fetch `official_url` only for picks that need it (see Step 2). No open-ended calendar trawling.
- **Minimal turns:** Read inputs → select → spot-check if needed → write briefing → update state → commit → push.

## Step 0 — Push guard

If triggered by a git push to `main`:

1. Inspect the **triggering commit only** (`git log -1 --name-only`, `git log -1 --format=%s`).
2. Consider only research files: `inbox/berlin-culture/YYYY-MM-DD-synthesis.json` or `inbox/berlin-culture/YYYY-MM-DD-raw.json`. Ignore `*-rss.json`, `*-wordpress.json`, `*-spend.json`, `*-spend-cap.error.txt`, `.gitkeep`.
3. If **no** research file above was added or modified in this commit, **stop** — log "No berlin-culture inbox research in this commit; skipping synthesis."
4. Decide if this commit is a **fresh pre-fetch** (continue) or **repo/test/migration** (stop):
   - **Continue** if the commit message starts with `inbox/berlin-culture:`.
   - **Else continue** only if a changed `*-synthesis.json` has `built_at` within the **last 24 hours** (UTC).
   - **Otherwise stop** — log "Inbox path changed but not a fresh pre-fetch; skipping synthesis."
5. If `briefings/berlin-culture/YYYY-MM-DD.md` exists for the inbox file's Tuesday date, **stop** — log "Briefing already exists; skipping duplicate synthesis." (`YYYY-MM-DD.test.md` is ignored — use that suffix for end-to-end tests; see README.)

## Step 1 — Read context

1. `.cursor/rules/berlin-culture-briefing-style.mdc`
2. `config/briefings/berlin-culture/topics.yaml` and `sources.yaml`
3. `state/berlin-culture/events_index.md`
4. Last **4** `briefings/berlin-culture/*.md` files (tone only)
5. `inbox/berlin-culture/YYYY-MM-DD-synthesis.json` (prefer today; fallback `*-raw.json` with warning)

## Step 2 — Select (light verification)

From the synthesis inbox:

1. Apply Tuesday briefing rule (events Wed → following Mon/Tue, or exhibitions open through Wed).
2. **Trust `verified: true` for reachability** — pre-fetch confirmed a deep event/exhibition URL plus concrete dates/times. Still apply the year check below for Top Picks.
3. **Browse only when required** — fetch `official_url` once, only for picks you plan to include that lack `verified: true` **or** match any of:
   - **Top Picks** (always spot-check — including verified items — for page year/dates)
   - `closing_soon: true` and not verified
   - Vague `dates` or `times` (e.g. "TBA", "various", "check website")
   - `official_url` looks like a homepage only (path is `/`, `/en`, or one shallow segment)
4. **Year / archive guard (mandatory):** When you fetch a page, confirm on-page event dates.
   - Prior-year archive page (e.g. July 2022 while briefing is 2026) → **drop**. Never rewrite dates forward into this week.
   - Current-year dates outside Wed–Tue → **Advance Radar** with the page’s real dates, or drop — do not invent in-week dates.
   - Prefer year-in-path URLs (`…/event-2026/`) over older archive slugs for the same show.
5. Drop items that fail a spot-check. Do **not** browse to find replacements.
6. Build a **selection table** (internal — do not commit this table) before drafting:

   | event_key | venue | series_id | section | notes |
   |-----------|-------|-----------|---------|-------|
   | normalized title+venue | … | from inbox `series_id` or blank | one primary section | |

   **Reject a row when:**
   - `event_key` already assigned → duplicate event (use Top Picks cross-reference only)
   - `series_id` already assigned and non-empty → festival/series cap (merge into existing entry)
   - venue already has **2** entries this week → venue cap (unless replacing a weaker pick)
   - item is in `events_index.md` without material change → anti-repetition

   Use inbox `series_id` and `event_kind` when present. Prefer `festival_event` / `single` items over `festival_overview` for section fills.

7. Apply venue diversification (~15–20% cap per venue) and **one event, one slot** (style rule).
8. Check `events_index.md` — skip repeats unless materially new.
9. Select final counts per section (see style rule). Compose **Top Picks** from the strongest items across sections — Top Picks must not be re-written as full entries elsewhere.
10. **Thin-week fallback** when a section is under target (see style rule): promote `advance_radar` into the week, omit the section, or cross-reference — never pad with duplicates or festival splits.
11. **Advance Radar** only if genuinely relevant; omit section otherwise.

Target: **≤5 URL fetches** per weekly run (typically Top Picks + closing-soon only). Top Pick year checks count toward this budget.

Title: `# Berlin Culture Briefing — Week of {start}–{end}, {year}` using `week_start` / `week_end` from inbox JSON when present.

Add a **1–2 sentence intro** immediately after the title (before `## Top Picks`): frame the week's connecting themes in plain prose — no bullets. This becomes the visible email opener and inbox preview.

Use per-entry format from the style rule (Title, Venue, Date(s), Time(s), Short Context, Why It Fits, Official Link).

## Step 3 — Validate briefing

Run before committing:

```bash
python scripts/validate_culture_briefing.py --path briefings/berlin-culture/YYYY-MM-DD.md
```

- **ERROR** (duplicate event, duplicate official link, festival listed twice): fix the briefing and re-run until clean.
- **WARN** (section below minimum count): acceptable if noted in `last_run.json` (`thin_sections` / `omitted_sections`); do not fix by duplicating picks.

## Step 4 — Update state

1. Append to `state/berlin-culture/events_index.md` (trim >8 weeks)
2. Update `state/berlin-culture/last_run.json` with `briefing_type`, `week_start`, `week_end`, paths, counts, `thin_sections`, `omitted_sections`, `validation_warnings` if any

## Step 5 — Commit and push

1. Stage: `briefings/berlin-culture/YYYY-MM-DD.md`, `state/berlin-culture/events_index.md`, `state/berlin-culture/last_run.json`
2. Commit: `briefing/berlin-culture: YYYY-MM-DD`
3. Push to `origin main`
