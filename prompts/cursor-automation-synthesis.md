# Cursor Automation — Daily Briefing Synthesis

Setup guide for [Cursor Automations](https://cursor.com/automations). **Runnable steps live in `prompts/synthesis-run.md`** — edit that file in git; the automation reads it from the repo each run.

## Automation settings

| Setting | Value |
|---------|--------|
| **Trigger** | GitHub → **New push to branch** → `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (or Cursor Fast). Avoid GPT 5.5 High — synthesis is rule-bound editing from pre-fetched inbox, not research. |
| **Spending cap** | ~$8–10/mo on-demand safety net |

Optional backup: cron `0 7 * * 1-5` UTC if pre-fetch was missed.

## Instructions (paste once into automation — do not edit here)

Paste **only** this block into the Cursor Automation instructions field. Never copy `synthesis-run.md` into the UI.

```
You are running the weekday daily briefing synthesis for inigober/briefings.

Your only job: read prompts/synthesis-run.md from the checked-out repo and execute every step (0–4) exactly as written. That file is the single source of truth — ignore any older instructions in this message.

Start by opening prompts/synthesis-run.md, then proceed in order.
```

### Why a pointer instead of the full prompt?

- Edit `prompts/synthesis-run.md` in git → next automation run picks it up automatically
- No copy-paste drift between repo and Cursor UI
- Same pattern as `.cursor/rules/` for editorial rules

**Important:** Push changes to `main` before the next inbox trigger if you want the new instructions used that day.

## Pipeline

```
Pre-fetch commits inbox/  →  push triggers this automation  →  synthesis commits briefings/  →  email workflow sends
```
