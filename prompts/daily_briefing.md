# Daily Briefing — Synthesis Instructions

Produce today's personal daily briefing. Read all inputs before writing.

## Inputs

1. `.cursor/rules/briefing-style.mdc` — mandatory editorial rules
2. `config/topics.yaml` — sections, limits, avoid lists, World geographic rules
3. `config/sources.yaml` — source priorities and Selected Reads mix
4. `inbox/YYYY-MM-DD-raw.json` — today's pre-fetched research (primary)
5. `state/dedup_index.md` — story/topic memory (~14 days)
6. `state/selected_reads_index.md` — article URL memory (5 briefings)
7. Last **7** files in `briefings/` — novelty and tone reference
8. `templates/daily_briefing.md` — output skeleton

## Philosophy

Maximize novelty for a daily reader. Reject stories already covered unless materially new. Prefer structural insight over headline churn.

## Section requirements

| Section | Stories | Notes |
|---------|---------|-------|
| Spain 🇪🇸 | 3 | See `avoid_unless_material` in topics.yaml |
| Germany 🇩🇪 | 3 | Same |
| Berlin 🏙️ | 3 | Local only |
| World 🌐 | 3 | ≥2 non-European regions; distinct from ES/DE |
| What Matters Today 🧠 | 3–4 themes | Not story summaries |
| Selected Reads 🗞️ | ~4 | Separate memory; source mix; Reuters/AP ≤1 |

## Story format

Each news story: bullet + bold headline, summary with `([Publisher][N])`, 🧭 and 🧩 lines, footnotes at file end.

## Rules

- Synthesize **only from inbox and config** unless inbox is empty (then note gap; do not browse).
- Run novelty test and anti-repetition checks before including any item.
- Selected Reads: never repeat a URL from last 5 briefings; do not duplicate today's news articles.
- World must not echo Spain/Germany topics.

## Outputs

1. `briefings/YYYY-MM-DD.md` — title format: `Daily Briefing — DD Month YYYY`
2. `state/dedup_index.md` — append stories/topics; trim >14 days
3. `state/selected_reads_index.md` — append URLs + titles; trim >5 briefings
4. `state/last_run.json` — date, status, paths, counts
5. Commit: `briefing: YYYY-MM-DD`

## Final checklist

Run the 10-point checklist in `briefing-style.mdc`. Revise before commit if any item fails.
