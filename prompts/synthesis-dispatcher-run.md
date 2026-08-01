# Briefing synthesis dispatcher — run instructions

Single source of truth for the **one** Cursor synthesis automation. Routes each push to at most one briefing type.

Known types: `news`, `berlin-culture`, `berlin-restaurants`, `music-discovery`.

## Cost discipline

- **Stop early:** Run the trigger script first; exit immediately on `skip`.
- **Inbox-first:** Prefer pre-fetched inbox files. Browse/fetch only when the per-type synthesis prompt requires it (e.g. culture Top Pick year spot-check, music URL confirmation). No open-ended research to fill gaps.
- **One type per run:** Never run two briefing syntheses in the same automation run.

## Step 0 — Route (mandatory)

1. From the repo root, run:
   ```bash
   python scripts/detect_synthesis_trigger.py --json
   ```
2. Parse the JSON:
   - If `type_id` is `null` or the script prints `skip`, log the `reason` and **stop** — do not read inbox or write briefings.
   - If `type_id` is set (`news`, `berlin-culture`, `berlin-restaurants`, or `music-discovery`), log which type and why, then continue.
3. Open the matching synthesis prompt from `config/briefings.yaml`:
   - `news` → `prompts/news/synthesis-run.md`
   - `berlin-culture` → `prompts/berlin-culture/synthesis-run.md`
   - `berlin-restaurants` → `prompts/berlin-restaurants/synthesis-run.md`
   - `music-discovery` → `prompts/music-discovery/synthesis-run.md`

**Do not** re-run Step 0 (push guard) from the per-type synthesis file — routing is already done.

## Step 1 — Execute per-type synthesis

Read the chosen `synthesis-run.md` and execute **all steps through commit and push**, including any Validate / Verify links step. Skip only that file’s **Step 0** (push guard) — routing already handled it.

## Step 2 — Confirm completion

Log the briefing type, output path, and commit SHA pushed to `main`.

If push fails, `git pull --rebase origin main` then push again. Do not mark success until the briefing is on `main`.
