# Cursor Automation — Berlin Restaurant Briefing Synthesis

Setup guide for [Cursor Automations](https://cursor.com/automations). **Runnable steps live in `prompts/berlin-restaurants/synthesis-run.md`.**

## Automation settings

| Setting | Value |
|---------|--------|
| **Trigger** | GitHub -> **New push to branch** -> `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (curation from pre-verified restaurant inbox) |
| **Spending cap** | ~$5-8/mo (weekly) |

Optional backup cron: `0 7 * * 4` UTC (Thursday 08:00 CET) if Thursday pre-fetch was missed.

## Instructions (paste once)

```
You are running the weekly Berlin restaurant briefing synthesis for inigober/briefings.

Your only job: read prompts/berlin-restaurants/synthesis-run.md from the checked-out repo and execute every step (0-4) exactly as written. That file is the single source of truth.

Start by opening prompts/berlin-restaurants/synthesis-run.md, then proceed in order.
```

## Pipeline

```
Thursday 07:00 CET pre-fetch commits inbox/berlin-restaurants/  ->  push triggers this automation  ->  briefing + email (~09:00 CET)
```

**Note:** This is a separate automation from the news and culture briefings. Push guards in each synthesis-run prevent cross-triggering.
