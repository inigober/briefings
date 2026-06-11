# Synthesis run instructions

Single source of truth for the daily briefing synthesis agent. Edit this file in git — do not duplicate steps in the Cursor Automation UI.

## Step 0 — Push guard (skip unrelated pushes)

If this run was triggered by a git push to `main`:

1. Inspect which files changed in the triggering push.
2. If **no** file under `inbox/` was added or modified, **stop immediately** — log "No inbox changes; skipping synthesis." and exit. Do not read files, write briefings, or commit.
3. If `briefings/YYYY-MM-DD.md` already exists for today's UTC date **and** inbox was not updated in this push, stop.

Only continue when fresh inbox research was just committed.

## Step 1 — Read context

1. `.cursor/rules/briefing-style.mdc`
2. `config/topics.yaml` and `config/sources.yaml`
3. `prompts/daily_briefing.md` and `templates/daily_briefing.md`
4. `state/dedup_index.md` and `state/selected_reads_index.md`
5. The **7 most recent** `briefings/*.md` files
6. `inbox/YYYY-MM-DD-raw.json` — prefer today's UTC date; if missing, use the most recent inbox file and flag it in the briefing
7. `inbox/YYYY-MM-DD-rss.json` if present — merge with raw for Selected Reads and thin sections

## Step 2 — Synthesize

Produce a novelty-first briefing with exactly these sections:

1. Spain 🇪🇸 (3 stories)
2. Germany 🇩🇪 (3 stories)
3. Berlin 🏙️ (3 stories, local only)
4. World 🌐 (3 stories, ≥2 non-European regions, distinct from ES/DE)
5. What Matters Today 🧠 (3–4 themes, not recaps)
6. Selected Reads 🗞️ (~4 items from inbox — incl. RSS think-tank/long-form; no separate pre-fetch; Reuters/AP ≤1)

Title: `# Daily Briefing — DD Month YYYY`

If inbox date ≠ briefing date, add under title: `*Research accessed DD Month YYYY.*`

Each news story: headline, summary, 💡 insight, 🧩 broader context, source link.

**Synthesize only from inbox and config.** Do not browse unless inbox is empty.

Apply anti-repetition: reject topics from dedup index unless materially new. Selected Reads: reject URLs in last 5 briefings.

## Step 3 — Update state

1. Append to `state/dedup_index.md` (trim >14 days)
2. Append to `state/selected_reads_index.md` (trim >5 briefings)
3. Update `state/last_run.json`

## Step 4 — Commit and push to GitHub main branch (required)

Run the final editorial checklist in `briefing-style.mdc` before committing.

1. Stage: `briefings/YYYY-MM-DD.md`, `state/dedup_index.md`, `state/selected_reads_index.md`, `state/last_run.json`
2. Commit message: `briefing: YYYY-MM-DD`
3. **Push to `origin main`** — this step is mandatory. The email workflow only runs after `briefings/*.md` lands on GitHub.
4. Confirm push succeeded (no unpushed commits). Log the commit SHA.

If push fails (auth, branch behind remote), `git pull --rebase origin main` then push again. Do not mark the run successful until `briefings/YYYY-MM-DD.md` is on `main`.
