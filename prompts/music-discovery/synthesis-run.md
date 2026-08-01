# Music discovery briefing — synthesis run instructions

Single source of truth for the weekly music discovery synthesis agent.

## Cost discipline

- **Single draft** after selection.
- **Trust taste inbox** — axes, recent taste, known labels, and skip list come from the personal export bridge.
- **Light discovery** — stop once you have 6 strong featured picks + 4 compact extras.
- **Minimal turns:** Read inputs → select → write briefing → update state → commit → push → write back personal recommendation log (local path).

## Step 0 — Push / trigger guard

If triggered by a git push to `main`:

1. Inspect the **triggering commit only** (`git log -1 --name-only`, `git log -1 --format=%s`).
2. Consider taste bridge files: `inbox/music-discovery/YYYY-MM-DD-context.json` or `inbox/music-discovery/YYYY-MM-DD-taste-snapshot.md`. Ignore `.gitkeep`.
3. If **no** bridge file above was added or modified in this commit, **stop**.
4. Fresh bridge check:
   - **Continue** if the commit message starts with `inbox/music-discovery:`.
   - **Else continue** only if a changed `*-context.json` has `built_at` within the **last 24 hours** (UTC).
   - **Otherwise stop**.
5. If `briefings/music-discovery/YYYY-MM-DD.md` exists for the inbox Friday date, **stop**. (`YYYY-MM-DD.test.md` is ignored.)

Local / manual runs may skip the push guard when the user explicitly asks to synthesize a date.

## Step 1 — Read context

1. `.cursor/rules/music-discovery-briefing-style.mdc`
2. `config/briefings/music-discovery/topics.yaml`
3. `state/music-discovery/releases_index.md`
4. Last **4** `briefings/music-discovery/*.md` files, if any
5. `inbox/music-discovery/YYYY-MM-DD-context.json` (prefer today's Friday date)
6. `inbox/music-discovery/YYYY-MM-DD-taste-snapshot.md`
7. Optional taste-profile excerpt only if axes are thin

Pay special attention to snapshot sections **Recent taste (24 months)** and **Familiar labels**, and context fields `recent_taste` / `known_labels`.

## Step 2 — Select

1. Load `skip_list` — do not recommend matching entries.
2. Load `library_skip.albums` — do not feature owned Spotify/YT/Rekordbox albums (fuzzy artist + release).
3. Load `known_labels` — demote to More listening unless trusted write-up exception.
4. Weight `recent_taste` (Rekordbox 24mo + Spotify adds/listening) over all-time crate lists.
5. Cross-check `releases_index.md`.
6. Build a pool that **mixes recent and older (aged-well)** releases; demote canon primers from Featured.
7. Enforce **max 1 entry per label** across featured + More listening.
8. Aim for **6 featured** (**3 club + 3 home**) + **4 More listening**.
9. Featured reception gate: **≥ ~4 weeks old OR trusted write-up**.
10. Captivation bar: every Featured pick must pass "would I leave this playing?"
11. Every featured pick needs: italicized label in title, cover, Genre + Listen on the **same line**, blank line, unlabeled context paragraph, blank line, Dig (with one link).
12. More listening: same compact favicon links (Bandcamp + verified YouTube when available), but **no `Listen:` label** — just the links after the sentence; italicize label names in the bold title segment.
13. **Album-first links** — Bandcamp `/album/…`; YouTube album/playlist over track; Spotify album last resort. Song links only for true singles. **YouTube only if verified**. Never Apple Music.
14. **Never invent Bandcamp (or other) URLs** — do not guess slugs from titles. Confirm every Listen, Dig, More listening, and cover URL by fetching the live page (or copying from a page you loaded). Dig links are not exempt. If unconfirmed, omit or use the label/artist Bandcamp homepage.
15. Internal table (do not commit):

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
   Every Listen, Dig, More listening, and cover URL must be HTTP-live. If it fails, fix or omit dead URLs — do not commit until it exits 0.
2. Stage briefing + state files
3. Commit: `briefing/music-discovery: YYYY-MM-DD`
4. **Push to `origin main`** — mandatory; email workflow triggers on `briefings/**/*.md`

## Step 5 — Write back recommendation memory (local path)

From personal repo, log each featured pick (and optionally more-listening) via `recommendation_memory.py log` after the briefing is on `main`.

Library uptake is detected later by `sync_taste.py` / `recommendation_memory.py reconcile` (auto `saved` / `owned`) — no manual mark step required from the reader.
