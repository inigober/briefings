# Cursor Automation — Berlin Culture Briefing Synthesis

Setup guide for [Cursor Automations](https://cursor.com/automations). **Runnable steps live in `prompts/berlin-culture/synthesis-run.md`.**

## Automation settings

| Setting | Value |
|---------|--------|
| **Trigger** | GitHub → **New push to branch** → `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (verification + curation from pre-fetched inbox) |
| **Spending cap** | ~$5–8/mo (weekly) |

Optional backup cron: `0 7 * * 2` UTC (Tuesday) if Tuesday pre-fetch was missed.

## Instructions (paste once)

```
You are running the weekly Berlin culture briefing synthesis for inigober/briefings.

Your only job: read prompts/berlin-culture/synthesis-run.md from the checked-out repo and execute every step (0–4) exactly as written. That file is the single source of truth.

Start by opening prompts/berlin-culture/synthesis-run.md, then proceed in order.
```

## Pipeline

```
Tuesday pre-fetch commits inbox/berlin-culture/  →  push triggers this automation  →  briefing + email
```

**Note:** This is a **separate** automation from the news briefing. Push guards in each synthesis-run prevent cross-triggering.
