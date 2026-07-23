# Music discovery briefing — synthesis run instructions

Single source of truth for the weekly music discovery synthesis agent.

## Cost discipline

- **Single draft** after selection.
- **Trust taste inbox** — axes and skip list come from the personal export bridge.
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

## Step 2 — Select

1. Load `skip_list` — do not recommend matching entries.
2. Load `library_skip.albums` — do not feature owned Spotify/YT/Rekordbox albums (fuzzy artist + release).
3. Cross-check `releases_index.md`.
4. Build a pool that **mixes recent and older (aged-well)** releases.
5. Enforce **max 1 entry per label** across featured + More listening.
6. Aim for **6 featured** + **4 More listening**.
7. Every featured pick needs: italicized label in title, cover, Genre + Listen on the **same line**, blank line, unlabeled context paragraph, blank line, Dig (with one link).
8. More listening: same compact favicon links (Bandcamp + verified YouTube when available), but **no `Listen:` label** — just the links after the sentence; italicize label names in the bold title segment.
9. **YouTube only if verified**. Spotify last resort; never Apple Music.
10. Internal table (do not commit):

   | slug | artist | release | label | year | era | genre | cover | bandcamp | youtube? | in_library? |

Title: `# Music Discovery Briefing — Week of YYYY-MM-DD`.

Intro → six `##` featured entries → `## More listening` (4 bullets). No closing summary section.

## Step 3 — Update state

1. Append featured + more-listening releases to `state/music-discovery/releases_index.md`; trim older than 12 weeks.
2. Update `state/music-discovery/last_run.json`.

## Step 4 — Commit and push

1. Stage briefing + state files
2. Commit: `briefing/music-discovery: YYYY-MM-DD`
3. Push to `origin main`

## Step 5 — Write back recommendation memory (local path)

From personal repo, log each featured pick (and optionally more-listening) via `recommendation_memory.py log` after the briefing is on `main`.
