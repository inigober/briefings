# Music discovery briefing — synthesis run instructions

Single source of truth for the weekly music discovery synthesis agent.

## Cost discipline

- **Single draft** after selection.
- **Trust pre-fetch only when verified:** Items with `"verified": true` have a live Bandcamp URL plus a cover (`cover_url` is Bandcamp art, sometimes fetched via Microlink when GitHub cannot open the album HTML). Copy Listen / Dig / cover / YouTube URLs **verbatim**.
- **No open-ended browsing.** Candidate discovery happens in `fetch_music_research.py` during Friday pre-fetch. If the verified pool is too thin, **stop without writing a briefing** (do not publish a gap placeholder).
- **Minimal turns:** Read inputs → select → write briefing → update state.

## Step 0 — Push / trigger guard

If triggered by a git push to `main`:

1. Inspect the **triggering commit only** (`git log -1 --name-only`, `git log -1 --format=%s`).
2. Consider only research files: `inbox/music-discovery/YYYY-MM-DD-synthesis.json` or `inbox/music-discovery/YYYY-MM-DD-raw.json`. Ignore `*-context.json`, `*-taste-snapshot.md`, `*-spend.json`, `.gitkeep`.
3. If **no** research file above was added or modified in this commit, **stop**.
4. Fresh research check:
   - **Continue** if the commit message starts with `inbox/music-discovery:`.
   - **Else continue** only if a changed `*-synthesis.json` (or `*-raw.json`) has `built_at` / `fetched_at` within the **last 24 hours** (UTC).
   - **Otherwise stop**.
5. If `briefings/music-discovery/YYYY-MM-DD.md` exists for the inbox Friday date, **stop**. (`YYYY-MM-DD.test.md` is ignored.)

Local / manual runs may skip the push guard when the user explicitly asks to synthesize a date.

## Step 1 — Read context

1. `.cursor/rules/music-discovery-briefing-style.mdc`
2. `config/briefings/music-discovery/topics.yaml`
3. `state/music-discovery/releases_index.md`
4. Last **4** `briefings/music-discovery/*.md` files, if any
5. `inbox/music-discovery/YYYY-MM-DD-synthesis.json` (prefer today's Friday date; fallback `*-raw.json` with warning)
6. Taste companion (do not treat as the candidate pool): `inbox/music-discovery/YYYY-MM-DD-context.json` and `YYYY-MM-DD-taste-snapshot.md`

Pay special attention to snapshot sections **Recent taste (24 months)** and **Familiar labels**, and inbox fields `known_label`, `mode`, `reception_ok`.

## Step 2 — Select

From the synthesis inbox:

1. Include only items with `"verified": true` **and a non-empty `cover_url`**. Skip cover-less rows.
2. Copy `bandcamp_url`, `cover_url`, `youtube_url`, and `dig_url` **exactly** as stored — never invent or slugify Bandcamp paths. If `youtube_url` is a `music.youtube.com/playlist?list=…` (or youtube.com playlist) string, include it on the Listen line. If it is `null`, omit YouTube — do not search YouTube yourself.
3. Load `skip_list` / `library_skip` from the taste companion — do not recommend matches (pre-fetch already filtered; double-check).
4. `known_label: true` → **More listening** unless `writeup_url` is present (trusted write-up exception).
5. Weight recent taste (snapshot) over all-time crate lists.
6. Cross-check `releases_index.md`.
7. Mix recent and aged-well (`era`); demote canon primers from Featured.
8. Enforce **max 1 entry per label** across featured + More listening.
9. Aim for **6 featured** (**3 club + 3 home** via `mode`) + **4 More listening**.
10. Featured reception gate: `reception_ok: true` (≥ ~4 weeks old OR `writeup_url`).
11. Captivation bar: every Featured pick must pass "would I leave this playing?"
12. Every featured pick needs: italicized label in title, cover from `cover_url`, Genre + Listen on the **same line** (Bandcamp + YouTube when `youtube_url` is set), blank line, unlabeled context (use/adapt `context`), blank line, Dig (`dig_sentence` + `dig_url`).
13. More listening: same compact favicon links, **no `Listen:` label**; italicize label names.
14. **Never invent URLs.** If a URL is missing in the inbox, omit that platform. Do not search.

If verified candidates cannot fill 6 featured + 4 More listening without inventing URLs, **do not write** `briefings/music-discovery/YYYY-MM-DD.md`.

Internal table (do not commit):

   | slug | artist | release | label | year | era | mode (club/home) | known_label? | reception_ok? | captivating? | cover | bandcamp | youtube_album? | in_library? |

Title: `# Music Discovery — Week of YYYY-MM-DD`.

Intro → six `##` featured entries → `## More listening` (4 bullets). No closing summary section.

## Step 3 — Update state

1. Append featured + more-listening releases to `state/music-discovery/releases_index.md`; trim older than 12 weeks.
2. Update `state/music-discovery/last_run.json`.

## Step 4 — Verify links, commit, and push (required)

1. Run link verification (must pass before commit):
   ```bash
   python scripts/verify_music_urls.py --type music-discovery --date YYYY-MM-DD
   ```
   Every Listen, Dig, More listening, and cover URL must be HTTP-live. The script also rejects gap/placeholder briefings. If it fails, fix or omit dead URLs — do not commit until it exits 0.
2. Stage briefing + state files
3. Commit: `briefing/music-discovery: YYYY-MM-DD`
4. **Push to `origin main`** — mandatory; email workflow triggers on `briefings/**/*.md`

Do not mark the run complete until the briefing commit is on `main`.

## Step 5 — Write back recommendation memory (local path)

From personal repo, log each featured pick (and optionally more-listening) via `recommendation_memory.py log` after the briefing is on `main`.

Library uptake is detected later by `sync_taste.py` / `recommendation_memory.py reconcile` (auto `saved` / `owned`) — no manual mark step required from the reader.
