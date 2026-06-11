# Daily Briefing — Synthesis Instructions

Produce today's personal daily briefing. Read all inputs before writing.

## Inputs

1. `.cursor/rules/briefing-style.mdc` — mandatory editorial rules
2. `config/topics.yaml` — sections, limits, avoid lists, World geographic rules
3. `inbox/YYYY-MM-DD-synthesis.json` — token-light pre-fetch slice (primary; fallback: `*-raw.json`)
4. `state/dedup_index.md` — story/topic memory (~14 days)
5. `state/selected_reads_index.md` — article URL memory (5 briefings)
6. Last **3** files in `briefings/` — tone reference only

Full runnable steps: `prompts/synthesis-run.md`.

## Philosophy

Maximize novelty for a daily reader. Reject stories already covered unless materially new. Prefer structural insight over headline churn.

The inbox is a **research warehouse** (~30–50 items from OpenAI + RSS). Items may include `ingestion_source: "rss"` (headlines only) or OpenAI items (richer summaries). Select the best 3 per section after dedup — if one section is thin after filtering, draw the next-best alternative from inbox rather than leaving gaps.

## Section requirements

| Section | Stories | Notes |
|---------|---------|-------|
| Spain 🇪🇸 | 3 | See `avoid_unless_material` in topics.yaml |
| Germany 🇩🇪 | 3 | Same |
| Berlin 🏙️ | 3 | Local only |
| World 🌐 | 3 | ≥2 non-European regions; distinct from ES/DE |
| What Matters Today 🧠 | 3–4 themes | Not story summaries |
| Selected Reads 🗞️ | ~4 | Pick from inbox (incl. RSS think-tank/long-form items); separate memory; Reuters/AP ≤1 |

## Story format

Each news story: bullet + bold headline, summary with `([Publisher][N])`, 💡 and 🧩 lines, footnotes at file end.

If inbox file date ≠ briefing date, add `*Research accessed DD Month YYYY.*` under the title and set `inbox_date` in `last_run.json`.

## Rules

- Synthesize **only from inbox and config** unless inbox is empty (then note gap; do not browse).
- **Selected Reads:** no longer pre-fetched — choose from inbox items (especially think-tank RSS, long-form, specialist outlets). Do not duplicate today's news stories.
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
