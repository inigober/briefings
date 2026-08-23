# Briefings repo — agent guide

Personal briefing pipeline: pre-fetch → synthesis → email.

## Pipeline

1. GitHub Actions pre-fetch writes `inbox/{type}/` and pushes to `main`.
   Music also runs OpenAI web_search here (`scripts/fetch_music_research.py`) so Codex does not need to browse.
2. Synthesis is requested by `.github/workflows/request-codex-synthesis.yml`, then Codex Cloud writes `briefings/{type}/YYYY-MM-DD.md` + `state/{type}/` to a PR branch.
3. `send-briefing-email.yml` emails on push of `briefings/**/*.md`.

Types: `news`, `berlin-culture`, `berlin-restaurants`, `music-discovery` (see `config/briefings.yaml`).

## Synthesis in Codex Cloud

When working on an `automation/synthesis-*` PR:

- Follow `prompts/codex-cloud-synthesis-run.md` and the type’s `prompts/{type}/synthesis-run.md`.
- Read `.github/synthesis-requests/*.json` for `type_id`, `date`, and source commit.
- **Do** `git commit` and push changes to the current synthesis PR branch after verification.
- **Do not** push to `main` or send email; merging the verified PR handles both downstream effects.
- **No web browsing** — synthesize from inbox/state/style rules only. Verification scripts run after you finish.
- Remove the synthesis request marker only after the production briefing and state updates are complete.
- Prefer minimal file reads; one draft pass.

## Commit message convention (workflow)

`briefing/{type}: YYYY-MM-DD`

## Editorial rules

The complete Cursor instruction set is mirrored in [`CURSOR_INSTRUCTIONS.md`](CURSOR_INSTRUCTIONS.md), including the PM handholding guidance and all briefing-specific editorial rules. This is the routine agent-readable copy. The original `.cursor/rules/{type}-briefing-style.mdc` files remain in place for Cursor compatibility.
