# Personal Daily Briefing

Repo-based, unattended daily briefing for a reader focused on **Spain, Germany, Berlin, and international affairs** — novelty-first, FT/Economist-style analysis.

Pipeline: **pre-fetch research → Cursor cloud synthesis → Resend email delivery**.

## Architecture

```
OpenAI web_search (GitHub Action, weekdays)
        ↓
   inbox/YYYY-MM-DD-raw.json
        ↓
Cursor Automation (cloud agent, weekdays)
        ↓
   briefings/YYYY-MM-DD.md + state updates
        ↓
GitHub Action on push → styled HTML email (Resend)
```

| Layer | Responsibility |
|-------|----------------|
| Repo files | Rules, topics, sources, dedup, history |
| `scripts/fetch_openai_research.py` | Breadth + publisher-domain research |
| Cursor Automation | Rule-bound synthesis, no repetition |
| `scripts/send_briefing_email.py` | Markdown → HTML → inbox |

## Repository layout

```
├── .cursor/rules/briefing-style.mdc   # editorial rules (always applied)
├── config/
│   ├── topics.yaml                    # sections and limits
│   └── sources.yaml                   # domains, RSS, newsletters
├── prompts/
│   ├── daily_briefing.md              # synthesis instructions
│   ├── research_brief.md              # OpenAI pre-fetch prompt
│   └── cursor-automation-synthesis.md # automation prompt draft
├── templates/daily_briefing.md        # output skeleton
├── briefings/YYYY-MM-DD.md            # committed daily outputs
├── state/
│   ├── last_run.json
│   ├── dedup_index.md              # story/topic memory (14 days)
│   └── selected_reads_index.md     # article URLs (5 briefings)
├── inbox/                             # raw research JSON
└── scripts/
    ├── fetch_openai_research.py
    └── send_briefing_email.py
```

## Setup

### 1. Briefing sections

Each edition follows this structure:

1. Spain 🇪🇸 (3 stories)
2. Germany 🇩🇪 (3 stories)
3. Berlin 🏙️ (3 stories, local)
4. World 🌐 (3 stories, ≥2 non-European regions)
5. What Matters Today 🧠 (3–4 themes)
6. Selected Reads 🗞️ (~4 curated articles)

Editorial rules live in `.cursor/rules/briefing-style.mdc`. Section-specific avoid lists and priorities in `config/topics.yaml`. Sources in `config/sources.yaml`.

### 2. GitHub secrets and variables

**Secrets** (Settings → Secrets and variables → Actions):

| Secret | Purpose |
|--------|---------|
| `OPENAI_API_KEY` | Research pre-fetch |
| `RESEND_API_KEY` | Email delivery |

**Variables**:

| Variable | Example | Purpose |
|----------|---------|---------|
| `OPENAI_RESEARCH_MODEL` | `gpt-4.1` | Pre-fetch model |
| `BRIEFING_FROM_EMAIL` | `briefing@yourdomain.com` | Resend sender |
| `BRIEFING_TO_EMAIL` | `you@example.com` | Recipient(s), comma-separated |

Resend free tier: 3,000 emails/mo, 100/day.

### 3. Cursor Automation (synthesis)

Create an automation in [Cursor Automations](https://cursor.com/automations):

- **Trigger:** Cron `0 7 * * 1-5` (weekdays — adjust timezone in editor)
- **Runtime:** Cloud agent
- **Repo:** This repository
- **Prompt:** Copy from `prompts/cursor-automation-synthesis.md`
- **Spending cap:** $10–15/mo on-demand safety net

Schedule pre-fetch **before** synthesis (workflow uses `30 6 * * 1-5` UTC).

### 4. Manual test run

```bash
# Research (requires OPENAI_API_KEY)
pip install -r scripts/requirements.txt
export OPENAI_API_KEY=sk-...
python scripts/fetch_openai_research.py --dry-run   # preview prompt
python scripts/fetch_openai_research.py             # write inbox/

# Synthesis — run Cursor automation manually or agent locally with prompts/daily_briefing.md

# Email preview (no send)
python scripts/send_briefing_email.py --file briefings/YYYY-MM-DD.md --dry-run
```

## Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `daily-briefing.yml` | Weekdays 06:30 UTC + manual | Pre-fetch → commit `inbox/` |
| `send-briefing-email.yml` | Push to `briefings/*.md` on `main` | Send styled email |

## Rollout checklist

- [ ] Fill in topics, sources, and editorial rules
- [ ] Add GitHub secrets/variables
- [ ] 3–4 manual synthesis runs; refine output
- [ ] Test pre-fetch vs ChatGPT coverage (1-week A/B)
- [ ] Verify email HTML in inbox
- [ ] Enable Cursor Automation cron
- [ ] Monitor [Cursor usage](https://cursor.com/dashboard?tab=cloud-agents) for 2 weeks

## Open items

Still to configure before going fully unattended:

- Cron time + timezone (workflows default to UTC)
- Email recipient(s) and Resend sending domain
- RSS feeds / newsletter forwards for paywalled subscriptions
- Optional tweaks to `avoid_unless_material` lists in `config/topics.yaml`
