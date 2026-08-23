# Cursor Automation — Briefing Synthesis (dispatcher)

Setup guide for [Cursor Automations](https://cursor.com/automations). **One automation** (e.g. **"Briefing synthesis"**) handles all briefing types. Runnable steps live in `prompts/synthesis-dispatcher-run.md`.

## Automation settings

| Setting | Value |
|---------|--------|
| **Name** | Briefing synthesis |
| **Trigger** | GitHub → **New push to branch** → `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (or Cursor Fast) |
| **Spending cap** | ~$10–15/mo safety net |

**Push trigger only.** Do not add schedule crons in Cursor. Pre-fetch timing is handled by cron-job.org → GitHub `workflow_dispatch` (see `docs/external-scheduling.md`). Use `prefetch-health-check.yml` for missed pre-fetch alerts.

If an existing “Briefing synthesis” automation is disabled, **re-enable it** with these settings. Do not create a second one.

## Instructions (paste once into automation)

Paste **only** this block. Never copy `synthesis-dispatcher-run.md` into the UI.

```
You are running the briefing synthesis dispatcher for inigober/briefings.

Your only job: read prompts/synthesis-dispatcher-run.md from the checked-out repo and execute every step exactly as written. That file is the single source of truth.

Start by opening prompts/synthesis-dispatcher-run.md, then proceed in order.
```

## Why a pointer instead of the full prompt?

- Edit `prompts/synthesis-dispatcher-run.md` in git → next automation run picks it up automatically
- No copy-paste drift between repo and Cursor UI
- Same pattern as `.cursor/rules/` for editorial rules

**Important:** Push changes to `main` before the next inbox trigger if you want the new instructions used that day.

## Pipeline

```
Pre-fetch commits inbox/{type}/  →  Cursor Automation (push to main)  →  briefings/{type}/  →  email
```

Types: `news`, `berlin-culture`, `berlin-restaurants`, `music-discovery`.

Missed pre-fetch? `prefetch-health-check.yml` emails you → run the matching `*-prefetch.yml` workflow manually.

Routing logic is testable locally:

```bash
python scripts/detect_synthesis_trigger.py --json
python scripts/detect_synthesis_trigger.py --json --backup
```

Per-type setup docs (`prompts/*/cursor-automation-synthesis.md`) are historical. Use this single dispatcher.
