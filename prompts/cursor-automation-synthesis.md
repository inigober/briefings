# Cursor Automation — Daily Briefing Synthesis

- **Trigger:** Cron `0 7 * * 1-5` (weekdays 07:00 UTC — adjust in editor)
- **Runtime:** Cloud agent
- **Repo:** This repository (GitHub integration enabled)
- **Model:** Cheaper/fast model when inbox is pre-fetched

---

## Prompt (paste into automation)

You are running the weekday daily briefing synthesis for this repo.

### Step 1 — Read context

1. `.cursor/rules/briefing-style.mdc`
2. `config/topics.yaml` and `config/sources.yaml`
3. `prompts/daily_briefing.md` and `templates/daily_briefing.md`
4. `state/dedup_index.md` and `state/selected_reads_index.md`
5. The **7 most recent** `briefings/*.md` files
6. `inbox/YYYY-MM-DD-raw.json` (today's date UTC)

### Step 2 — Synthesize

Produce a novelty-first briefing with exactly these sections:

1. Spain 🇪🇸 (3 stories)
2. Germany 🇩🇪 (3 stories)
3. Berlin 🏙️ (3 stories, local only)
4. World 🌐 (3 stories, ≥2 non-European regions, distinct from ES/DE)
5. What Matters Today 🧠 (3–4 themes, not recaps)
6. Selected Reads 🗞️ (~4 items, diversified mix, Reuters/AP ≤1)

Title: `# Daily Briefing — DD Month YYYY`

Each news story: headline, summary, 🧭 Why it matters, 🧩 Broader context, source link.

**Synthesize only from inbox and config.** Do not browse unless inbox is empty.

Apply anti-repetition: reject topics from dedup index unless materially new. Selected Reads: reject URLs in last 5 briefings.

### Step 3 — Update state

1. Append to `state/dedup_index.md` (trim >14 days)
2. Append to `state/selected_reads_index.md` (trim >5 briefings)
3. Update `state/last_run.json`

### Step 4 — Commit

Message: `briefing: YYYY-MM-DD`

Files: `briefings/YYYY-MM-DD.md`, `state/dedup_index.md`, `state/selected_reads_index.md`, `state/last_run.json`.

Run the final editorial checklist in `briefing-style.mdc` before committing.
