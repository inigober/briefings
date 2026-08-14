# GitHub Actions + Codex — briefing synthesis

Runnable instructions for `.github/workflows/synthesize-briefing.yml`. The workflow already ran `scripts/detect_synthesis_trigger.py` and wrote `.synthesis-ci-context.json`.

## Hard constraints (CI)

1. **No git commit / push.** Write briefing + state files only. The workflow verifies URLs, then commits and pushes.
2. **No web browsing / open-ended research.** Use inbox + state + style rules. Spot-checks that need the live web are skipped here; HTTP verification runs in CI after you finish.
3. **One type only.** Use `type_id` from `.synthesis-ci-context.json`.
4. **Single draft.** Do not rewrite whole sections unless a local checklist item fails.

## Steps

### 1 — Read context

Open `.synthesis-ci-context.json` and note:

- `type_id` — `news` | `berlin-culture` | `berlin-restaurants` | `music-discovery`
- `date` — `YYYY-MM-DD` for the briefing filename
- `matched_files` — inbox inputs

### 2 — Run per-type synthesis (skip push guard)

Open the matching file and execute **from Step 1 through state updates**, including any *local* selection/checklist work:

| type_id | prompt |
|---------|--------|
| news | `prompts/news/synthesis-run.md` |
| berlin-culture | `prompts/berlin-culture/synthesis-run.md` |
| berlin-restaurants | `prompts/berlin-restaurants/synthesis-run.md` |
| music-discovery | `prompts/music-discovery/synthesis-run.md` |

**Skip:**

- That file’s **Step 0** (push guard)
- Any **commit / push** instructions
- Music **Step 5** (personal recommendation log on another machine)
- Culture web spot-checks that require browsing (use inbox evidence instead; note gaps in the briefing if needed)

**Still do:** write `briefings/{type}/{date}.md` and update the `state/{type}/` files listed in the type prompt.

### 3 — Self-check before finishing

- Briefing path exists: `briefings/{type_id}/{date}.md`
- Footnote / Official Link / Maps / Listen URLs are copied from inbox — never invented
- State files updated per the type prompt
- Do **not** create `*.test.md` unless the context says this is an end-to-end test

### 4 — Final message

Print a short summary:

```
type_id: …
date: …
briefing: briefings/…/….md
state_updated: yes/no
notes: …
```

Then stop. The workflow runs verification scripts and commits.
