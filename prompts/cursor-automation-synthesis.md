# Cursor Automation — Briefing Synthesis (dispatcher)

Setup guide for [Cursor Automations](https://cursor.com/automations). **One automation** (e.g. **"Briefing synthesis"**) replaces three per-type automations. Runnable steps live in `prompts/synthesis-dispatcher-run.md`.

## Automation settings

| Setting | Value |
|---------|--------|
| **Name** | Briefing synthesis (or similar) |
| **Trigger** | GitHub → **New push to branch** → `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (or Cursor Fast) |
| **Spending cap** | ~$10–15/mo safety net |

**Push trigger only.** Do not add schedule/backup crons — they add ~30+ low-value agent runs per month and do not help when pre-fetch itself was missed. Use `prefetch-health-check.yml` (GitHub) for missed pre-fetch alerts; recover manually or re-run pre-fetch from Actions.

## Instructions (paste once into automation)

Paste **only** this block. Never copy `synthesis-dispatcher-run.md` into the UI.

```
You are running the briefing synthesis dispatcher for inigober/briefings.

Your only job: read prompts/synthesis-dispatcher-run.md from the checked-out repo and execute every step exactly as written. That file is the single source of truth.

Start by opening prompts/synthesis-dispatcher-run.md, then proceed in order.
```

## Migration from three automations

1. **Disable** (do not delete yet) the old push-triggered automations for news, berlin-culture, and berlin-restaurants.
2. Create **one** new automation with the settings and instructions above.
3. After one successful daily/weekly cycle, delete the old automations.

Per-type setup docs (`prompts/*/cursor-automation-synthesis.md`) are kept for reference only.

## Pipeline

```
Pre-fetch commits inbox/{type}/  →  push triggers ONE dispatcher  →  synthesis commits briefings/{type}/  →  email workflow sends
```

Missed pre-fetch? `prefetch-health-check.yml` emails you → run the matching `*-prefetch.yml` workflow manually.

Routing logic is testable locally:

```bash
python scripts/detect_synthesis_trigger.py --json
```
