# Berlin culture briefing — synthesis run instructions

Single source of truth for the weekly Berlin culture briefing synthesis agent.

## Cost discipline

- **Single draft** after verification passes.
- **Verify only:** Fetch each candidate's `official_url` from the inbox to confirm date/time/availability. No open-ended browsing or calendar trawling.
- **Minimal turns:** Read inputs → verify picks → write briefing → update state → commit → push.

## Step 0 — Push guard

If triggered by a git push to `main`:

1. Inspect which files changed.
2. If **no** file under `inbox/berlin-culture/` was added or modified, stop — log "No berlin-culture inbox changes; skipping synthesis."
3. If `briefings/berlin-culture/YYYY-MM-DD.md` exists for today's UTC date **and** inbox was not updated in this push, stop.

## Step 1 — Read context

1. `.cursor/rules/berlin-culture-briefing-style.mdc`
2. `config/briefings/berlin-culture/topics.yaml` and `sources.yaml`
3. `state/berlin-culture/events_index.md`
4. Last **4** `briefings/berlin-culture/*.md` files (tone only)
5. `inbox/berlin-culture/YYYY-MM-DD-synthesis.json` (prefer today; fallback `*-raw.json` with warning)

## Step 2 — Verify and select

From the synthesis inbox:

1. Apply Tuesday briefing rule (events Wed → following Mon/Tue, or exhibitions open through Wed).
2. For each candidate you plan to include, **fetch `official_url`** and confirm it is still valid. Drop unconfirmed or stale items.
3. Apply venue diversification (~15–20% cap per venue).
4. Check `events_index.md` — skip repeats unless materially new.
5. Select final counts per section (see style rule). Compose **Top Picks** from the strongest verified items across sections.
6. **Advance Radar** only if genuinely relevant; omit section otherwise.

Title: `# Berlin Culture Briefing — Week of {start}–{end}, {year}` using `week_start` / `week_end` from inbox JSON when present.

Use per-entry format from the style rule (Title, Venue, Date(s), Time(s), Short Context, Why It Fits, Official Link).

## Step 3 — Update state

1. Append to `state/berlin-culture/events_index.md` (trim >8 weeks)
2. Update `state/berlin-culture/last_run.json` with `briefing_type`, `week_start`, `week_end`, paths, counts

## Step 4 — Commit and push

1. Stage: `briefings/berlin-culture/YYYY-MM-DD.md`, `state/berlin-culture/events_index.md`, `state/berlin-culture/last_run.json`
2. Commit: `briefing/berlin-culture: YYYY-MM-DD`
3. Push to `origin main`
