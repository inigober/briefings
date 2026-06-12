# Cursor Automation — Briefing Synthesis (dispatcher)

Setup guide for [Cursor Automations](https://cursor.com/automations). **One automation** (e.g. **"Briefing synthesis"**) replaces three per-type automations. Runnable steps live in `prompts/synthesis-dispatcher-run.md`.

## Automation settings

| Setting | Value |
|---------|--------|
| **Name** | Briefing synthesis (or similar) |
| **Trigger 1** | GitHub → **New push to branch** → `main` |
| **Trigger 2** | **Schedule** — backup crons below (add each as a separate schedule trigger) |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (or Cursor Fast) |
| **Spending cap** | ~$10–15/mo combined safety net |

### Backup schedule crons (UTC)

Add these in the automation **Triggers → Schedule** section. They catch missed synthesis when pre-fetch landed but push-triggered synthesis did not run.

| Type | Cron (UTC) | Local (approx.) |
|------|------------|-----------------|
| News | `5 7 * * *` | daily ~08:05 CET / ~09:05 CEST |
| Berlin culture | `5 7 * * 2` | Tuesday ~08:05 CET |
| Berlin restaurants | `5 8 * * 4` | Thursday ~09:05 CET / ~10:05 CEST |

**PM analogy:** Push trigger = normal doorbell when research arrives. Backup cron = a second doorbell that rings later if the briefing still is not written.

## Instructions (paste once into automation)

Paste **only** this block. Never copy `synthesis-dispatcher-run.md` into the UI.

```
You are running the briefing synthesis dispatcher for inigober/briefings.

Your only job: read prompts/synthesis-dispatcher-run.md from the checked-out repo and execute every step exactly as written. That file is the single source of truth.

Start by opening prompts/synthesis-dispatcher-run.md, then proceed in order.
```

## Adding backup crons to an existing automation

1. Go to [https://cursor.com/automations](https://cursor.com/automations)
2. Open **Briefing synthesis** (or your dispatcher automation)
3. Under **Triggers**, click **Add trigger** → **Schedule**
4. Paste the news cron: `5 7 * * *` → save
5. Repeat for culture (`5 7 * * 2`) and restaurants (`5 8 * * 4`) if you run those briefings
6. Confirm the automation is **Enabled**

## Migration from three automations

1. **Disable** (do not delete yet) the old push-triggered automations for news, berlin-culture, and berlin-restaurants.
2. Create **one** new automation with the settings and instructions above.
3. After one successful daily/weekly cycle, delete the old automations.

Per-type setup docs (`prompts/*/cursor-automation-synthesis.md`) are kept for reference only.

## Pipeline

```
Pre-fetch commits inbox/{type}/  →  push triggers ONE dispatcher  →  synthesis commits briefings/{type}/  →  email workflow sends
                                      ↑
                         backup cron re-runs dispatcher if inbox exists but briefing does not
```

Routing logic is testable locally:

```bash
python scripts/detect_synthesis_trigger.py --json
python scripts/detect_synthesis_trigger.py --json --backup
```
