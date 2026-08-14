# Cursor Automation — Briefing Synthesis (DEPRECATED)

> **Deprecated (2026-08).** Synthesis now runs in GitHub Actions via
> `.github/workflows/synthesize-briefing.yml` + OpenAI Codex (`openai/codex-action`).
> Runnable CI instructions: `prompts/github-synthesis-run.md`.
>
> **Action for you:** In [Cursor Automations](https://cursor.com/automations), **disable**
> (then later delete) the old “Briefing synthesis” automation so it does not double-run
> beside the GitHub Action.

The historical setup below is kept for reference only.

---

## Former automation settings

| Setting | Value |
|---------|--------|
| **Name** | Briefing synthesis (or similar) |
| **Trigger** | GitHub → **New push to branch** → `main` |
| **Repo** | `inigober/briefings` |
| **Runtime** | Cloud agent |
| **Model** | **Composer 2.5** (or Cursor Fast) |
| **Spending cap** | ~$10–15/mo safety net |

**Push trigger only.** Pre-fetch timing is handled by cron-job.org → GitHub `workflow_dispatch` (see `docs/external-scheduling.md`).

## Former instructions (do not recreate)

```
You are running the briefing synthesis dispatcher for inigober/briefings.

Your only job: read prompts/synthesis-dispatcher-run.md from the checked-out repo and execute every step exactly as written. That file is the single source of truth.

Start by opening prompts/synthesis-dispatcher-run.md, then proceed in order.
```

## Current pipeline

```
Pre-fetch commits inbox/{type}/  →  synthesize-briefing.yml (Codex)  →  briefings/{type}/  →  email
```

Routing logic is still testable locally:

```bash
python scripts/detect_synthesis_trigger.py --json
python scripts/detect_synthesis_trigger.py --json --backup
```
