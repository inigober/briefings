# Briefings repo — agent guide

Personal briefing pipeline: pre-fetch → synthesis → email.

## Agent operating principle

Take ownership of requested work end to end. Inspect the repository and connected services, implement the necessary changes, run the relevant tests or smoke checks, and verify the result before handing work back. Minimize requests for user intervention; ask only for approvals, credentials, or account actions that cannot be performed from the workspace, and give precise step-by-step instructions when one is required.

## Pipeline

1. GitHub Actions pre-fetch writes `inbox/{type}/` and pushes to `main`.
   Music also runs OpenAI web_search here (`scripts/fetch_music_research.py`) so synthesis can copy verified Listen / cover URLs instead of browsing.
2. **Cursor Automation** (“Briefing synthesis”) sees that push, routes with `prompts/synthesis-dispatcher-run.md`, and writes `briefings/{type}/YYYY-MM-DD.md` + `state/{type}/`.
3. `send-briefing-email.yml` emails on push of `briefings/**/*.md`.

Types: `news`, `berlin-culture`, `berlin-restaurants`, `music-discovery` (see `config/briefings.yaml`).

## Synthesis in Cursor Automation

When this run was triggered by a push to `main`:

- Follow `prompts/synthesis-dispatcher-run.md`, then the type’s `prompts/{type}/synthesis-run.md`.
- **Do** `git commit` and push to `main` after verification scripts pass.
- **Do not** send email; the email workflow handles delivery.
- Prefer inbox/state/style rules. Browse only when a type prompt requires a spot-check (culture Top Picks). Music URLs come from the verified synthesis inbox — do not invent slugs.
- Prefer minimal file reads; one draft pass.

## Commit message convention

`briefing/{type}: YYYY-MM-DD`

## Editorial rules

Style lives in `.cursor/rules/{type}-briefing-style.mdc` (paths are historical; still the source of truth).
