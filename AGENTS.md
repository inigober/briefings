# Briefings repo — agent guide

Personal briefing pipeline: pre-fetch → synthesis → email.

## Pipeline

1. GitHub Actions pre-fetch writes `inbox/{type}/` and pushes to `main`.
2. Synthesis (GitHub Action + Codex) writes `briefings/{type}/YYYY-MM-DD.md` + `state/{type}/`.
3. `send-briefing-email.yml` emails on push of `briefings/**/*.md`.

Types: `news`, `berlin-culture`, `berlin-restaurants`, `music-discovery` (see `config/briefings.yaml`).

## Synthesis in CI

When running under `.github/workflows/synthesize-briefing.yml`:

- Follow `prompts/github-synthesis-run.md` and the type’s `prompts/{type}/synthesis-run.md`.
- Read `.synthesis-ci-context.json` for `type_id` and `date`.
- **Do not** `git commit` or `git push` — the workflow does that after verification.
- **No web browsing** — synthesize from inbox/state/style rules only. Verification scripts run after you finish.
- Skip each type’s Step 0 push guard; routing already happened.
- Prefer minimal file reads; one draft pass.

## Commit message convention (workflow)

`briefing/{type}: YYYY-MM-DD`

## Editorial rules

Style lives in `.cursor/rules/{type}-briefing-style.mdc` (paths are historical; still the source of truth).
