# Berlin restaurant briefing — synthesis run instructions

Single source of truth for the weekly Berlin restaurant briefing synthesis agent.

## Cost discipline

- **Single draft** after selection.
- **Trust pre-fetch only when verified:** Items with `"verified": true` passed Google Places API checks when `GOOGLE_MAPS_API_KEY` is configured (`maps_api_verified: true`). Do not recommend unverified restaurants.
- **No open-ended browsing:** If the verified candidate pool is thin, write a shorter briefing rather than searching broadly.
- **Minimal turns:** Read inputs -> select -> write briefing -> update state -> commit -> push.

## Step 0 — Push guard

If triggered by a git push to `main`:

1. Inspect the **triggering commit only** (`git log -1 --name-only`, `git log -1 --format=%s`).
2. Consider only research files: `inbox/berlin-restaurants/YYYY-MM-DD-synthesis.json` or `inbox/berlin-restaurants/YYYY-MM-DD-raw.json`. Ignore `*-spend.json`, `*-spend-cap.error.txt`, `.gitkeep`.
3. If **no** research file above was added or modified in this commit, **stop** — log "No berlin-restaurants inbox research in this commit; skipping synthesis."
4. Decide if this commit is a **fresh pre-fetch**:
   - **Continue** if the commit message starts with `inbox/berlin-restaurants:`.
   - **Else continue** only if a changed `*-synthesis.json` has `built_at` within the **last 24 hours** (UTC).
   - **Otherwise stop** — log "Inbox path changed but not a fresh pre-fetch; skipping synthesis."
5. If `briefings/berlin-restaurants/YYYY-MM-DD.md` exists for the inbox file's Thursday date, **stop** — log "Briefing already exists; skipping duplicate synthesis." (`YYYY-MM-DD.test.md` is ignored — use that suffix for end-to-end tests; see README.)

## Step 1 — Read context

Read these files, in order:

1. `config/briefings/berlin-restaurants/style-rules.md`
2. `config/briefings/berlin-restaurants/topics.yaml` and `sources.yaml`
3. `state/berlin-restaurants/restaurants_index.md`
4. `inbox/berlin-restaurants/YYYY-MM-DD-synthesis.json` (prefer today's Thursday date; fallback `*-raw.json` with warning)

## Step 2 — Select

From the synthesis inbox:

1. Include only items with `"verified": true` (and `maps_api_verified: true` when present in the inbox).
2. Exclude candidates whose Google Maps fields suggest ambiguity, closure, relocation outside Berlin, or non-Berlin location.
3. Apply anti-repetition using `restaurants_index.md`; avoid repeating restaurants from the last **10 weekly briefings** unless there is a material reason. Repeats after 10 weeks are fine.
4. Select mostly affordable and mid-range restaurants. Include at most one fine dining item.
5. Diversify neighborhoods. Avoid more than two final recommendations from the same neighborhood unless the candidate pool makes that unavoidable.
6. Prioritize clear culinary identity, strong value, regional specificity, technical execution, and flavor over hype.
7. Include weaknesses and an honest verdict. Do not make every entry sound exceptional.
8. Write each entry as its own piece, following the **Voice** and **Comparisons** sections of the style rule: no references to previous briefings, no chained comparisons to other restaurants, no pipeline vocabulary.

Target final briefing: 6-8 restaurant entries. Aim for at least 6 whenever the verified pool has enough eligible candidates after the rules above; go shorter only when the pool is genuinely thin, not out of caution.

Title: `# Berlin Restaurant Briefing — Week of YYYY-MM-DD`.

Intro: 1–2 sentences on the week's food through-line for the email reader. **Do not** mention verified pool, Google Places, candidate counts, inbox, pre-fetch, or excluded repeats.

Use the exact per-entry format from the style rule:

`### Restaurant Name — Neighborhood — € / €€ / €€€ / €€€€`

Add `(good value)` or `(potentially overpriced)` only when the candidate has that exact `value_label`.

After each `###` heading, add email metadata from the inbox item (omit lines when null):
- `**Hours:**` from `google_maps_hours_compact` (already shortened, e.g. `Tue–Sun 12:00–22:00 (closed Mon)` — copy verbatim; if a range is clearly a data glitch, such as opening at 04:00 for a dinner restaurant, omit the Hours line rather than print it)
- `**Rating:**` from `google_maps_rating` and `google_maps_review_count` (format `4.5 (412)`)
- `**Maps:**` from `google_maps_url`

Then add `### New openings to watch` from the inbox `openings` list, following the **New Openings to Watch** section of the style rule (article link only, no Maps/verdict, omit the section if nothing qualifies). Do not browse to expand these.

End with `### This week's strongest bets` and choose three from the current briefing.

## Step 3 — Update state

1. Append included restaurants to `state/berlin-restaurants/restaurants_index.md`; trim entries older than 10 weeks.
2. Update `state/berlin-restaurants/last_run.json` with `briefing_type`, date, paths, counts, and selected restaurant names.
3. If the briefing has a "New openings to watch" section, append each linked article to `state/berlin-restaurants/openings_reported.json` (a JSON list of `{"url": "<article url>", "date": "YYYY-MM-DD"}`; create it as `[]` first if missing) and drop entries older than 60 days. The pre-fetch skips these links next time so the same article is never listed twice. If the section was omitted, leave the file unchanged.

## Step 4 — Verify Maps URLs, commit, and push (required)

1. Run Maps verification (must pass before commit):
   ```bash
   python scripts/verify_restaurant_briefing_sources.py --type berlin-restaurants --date YYYY-MM-DD
   ```
   Every `**Maps:**` URL must match a `google_maps_url` from the verified synthesis inbox, and every link under "New openings to watch" must match an `openings[].url`. If it fails, fix URLs — do not invent links or add out-of-inbox restaurants.
2. Stage: `briefings/berlin-restaurants/YYYY-MM-DD.md`, `state/berlin-restaurants/restaurants_index.md`, `state/berlin-restaurants/last_run.json`, and `state/berlin-restaurants/openings_reported.json` when changed
3. Commit: `briefing/berlin-restaurants: YYYY-MM-DD`
4. **Push to `origin main`** — mandatory; email workflow triggers on `briefings/**/*.md`

If push fails, `git pull --rebase origin main` then push again. Do not mark success until the briefing is on `main`.
