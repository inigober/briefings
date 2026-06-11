# Personal Briefings

Repo-based briefing platform: **news** (daily) and **Berlin culture** (weekly). Novelty-first editorial, automated pre-fetch, Cursor cloud synthesis, Resend email.

## Architecture

```
config/briefings.yaml          ← registry (paths, schedules, prompts)
        ↓
┌───────────────────────────────────────────────────────────────┐
│ news (daily)                                                  │
│   RSS + OpenAI → inbox/news/ → synthesis → briefings/news/    │
├───────────────────────────────────────────────────────────────┤
│ berlin-culture (Tuesday)                                      │
│   OpenAI → inbox/berlin-culture/ → synthesis → briefings/…   │
└───────────────────────────────────────────────────────────────┘
        ↓
GitHub Action on push → styled HTML email (Resend, same recipient)
```

| Layer | Responsibility |
|-------|----------------|
| `config/briefings.yaml` | Briefing type registry |
| `config/briefings/{type}/` | Topics, sources per type |
| Pre-fetch scripts | Research → typed `inbox/` |
| Cursor Automations | Rule-bound synthesis (one per type) |
| `scripts/send_briefing_email.py` | Markdown → HTML → inbox |

## Repository layout

```
├── config/
│   ├── briefings.yaml                 # type registry
│   └── briefings/
│       ├── news/                      # topics.yaml, sources.yaml
│       └── berlin-culture/
├── .cursor/rules/
│   ├── news-briefing-style.mdc
│   └── berlin-culture-briefing-style.mdc
├── prompts/
│   ├── news/synthesis-run.md
│   └── berlin-culture/synthesis-run.md
├── inbox/{type}/                      # pre-fetch JSON
├── briefings/{type}/                  # committed outputs
├── state/{type}/                      # dedup / events memory
└── scripts/
    ├── briefing_paths.py
    ├── fetch_openai_research.py       # news
    ├── fetch_culture_research.py      # berlin-culture
    └── slim_inbox_for_synthesis.py
```

## For PMs (learning as you go)

| You care about | File / place |
|----------------|--------------|
| Which briefings exist | `config/briefings.yaml` |
| News editorial rules | `.cursor/rules/news-briefing-style.mdc` |
| Culture editorial rules | `.cursor/rules/berlin-culture-briefing-style.mdc` |
| News topics & sources | `config/briefings/news/` |
| Culture topics & sources | `config/briefings/berlin-culture/` |
| News synthesis steps | `prompts/news/synthesis-run.md` |
| Culture synthesis steps | `prompts/berlin-culture/synthesis-run.md` |
| News pre-fetch schedule | `.github/workflows/news-prefetch.yml` |
| Culture pre-fetch (Tuesdays) | `.github/workflows/berlin-culture-prefetch.yml` |
| OpenAI pre-fetch spend cap | `scripts/openai_spend.py`, `OPENAI_DAILY_SPEND_CAP_USD` |
| Email delivery | `.github/workflows/send-briefing-email.yml` |

## Briefing types

### News Briefing (daily)

Sections: Spain, Germany, Berlin, World, What Matters Today, Selected Reads.

Title: `# News Briefing — DD Month YYYY`

### Berlin Culture Briefing (weekly, Tuesday)

Sections: Top Picks, Exhibitions, Film, Performing Arts, Music, Wildcards, Advance Radar (optional).

Title: `# Berlin Culture Briefing — Week of June 16–22, 2026`

## Setup

### GitHub secrets and variables

**Secrets:** `OPENAI_API_KEY`, `RESEND_API_KEY`

**Variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_RESEARCH_MODEL` | `gpt-4.1` | Pre-fetch model |
| `OPENAI_DAILY_SPEND_CAP_USD` | `2` (built-in default) | Hard daily cap for OpenAI pre-fetch. **Optional** — only add this variable if you want a value other than $2; no code change needed. |
| `BRIEFING_FROM_EMAIL` | — | Resend sender (briefing email + spend-cap alerts) |
| `BRIEFING_TO_EMAIL` | — | Recipient |

Both briefing types email the **same recipient**; subjects come from each briefing's H1 title.

### OpenAI pre-fetch spend cap

Pre-fetch scripts (`fetch_openai_research.py`, `fetch_culture_research.py`) track **estimated** daily OpenAI spend and **abort** when the cap is reached.

**Default cap: $2/day** per briefing type (UTC date), hard-coded in `scripts/openai_spend.py` and the pre-fetch workflows. You do **not** need to create a GitHub variable unless you want a different limit.

**To change the cap without touching code:** repo **Settings → Secrets and variables → Actions → Variables** → add or edit `OPENAI_DAILY_SPEND_CAP_USD` (e.g. `3`). The next pre-fetch run picks it up.

| What | Where |
|------|--------|
| Default ($2) | `scripts/openai_spend.py` + workflow shell fallback |
| Change cap (no deploy) | GitHub variable `OPENAI_DAILY_SPEND_CAP_USD` |
| Local override | `export OPENAI_DAILY_SPEND_CAP_USD=3` before running scripts |
| Per-section usage logs | GitHub Action log output |
| Daily ledger (committed) | `inbox/{type}/YYYY-MM-DD-spend.json` |
| Cap abort marker | `inbox/{type}/YYYY-MM-DD-spend-cap.error.txt` |

**When the cap is hit:**

1. Pre-fetch stops immediately (no `*-raw.json` for that run)
2. The GitHub workflow **fails** (enable [Actions failure notifications](https://docs.github.com/en/account-and-profile/managing-subscriptions-and-notifications-on-github/setting-up-notifications/configuring-notifications#github-actions-notifications) on your GitHub profile)
3. An **email alert** is sent via Resend if `RESEND_API_KEY` + `BRIEFING_*` are set (same credentials as briefing delivery)
4. The spend ledger is committed so a manual re-run the same day does not bypass the cap

Costs are **estimates** from API token usage + web-search call counts (see `scripts/openai_spend.py`). Pair with [OpenAI billing alerts](https://platform.openai.com/settings/organization/limits) as a platform-level backstop.

**PM analogy:** Repo cap = circuit breaker on the research wire. OpenAI billing limits = utility company shutoff. Cursor synthesis cap = separate editor budget.

### Cursor Automations (synthesis)

Create **two** automations in [Cursor Automations](https://cursor.com/automations):

| Automation | Pointer prompt |
|------------|----------------|
| News | `prompts/news/cursor-automation-synthesis.md` |
| Berlin culture | `prompts/berlin-culture/cursor-automation-synthesis.md` |

Each automation: trigger on push to `main`, cloud agent, paste the short pointer block once.

Push guards in each `synthesis-run.md` ensure only the matching inbox change triggers work.

### Schedules

| Workflow | Cron (UTC) | Local (CET) |
|----------|------------|-------------|
| `news-prefetch.yml` | `30 5 * * *` | 06:30 daily |
| `berlin-culture-prefetch.yml` | `0 5 * * 2` | 06:00 Tuesday |

Synthesis is push-triggered (inbox commit). Optional backup crons on each automation if pre-fetch was missed.

### Local OpenAI API key (safe setup)

**A `.env` file in the repo is not a security risk** as long as it stays **local only**:

| Safe | Unsafe |
|------|--------|
| `.env` on your Mac (listed in `.gitignore`) | Committing `.env` to git |
| `cp .env.example .env` and paste your key | Pasting keys into tracked files (README, YAML, prompts) |
| GitHub secret `OPENAI_API_KEY` for Actions | Sharing `.env` in Slack/email |

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY=sk-...

set -a && source .env && set +a
python3 scripts/fetch_culture_research.py --type berlin-culture --date 2026-06-09
```

**PM analogy:** `.env` is like a sticky note on your desk — fine at home; never photocopy it into the employee handbook (the repo).

### Manual test

```bash
pip install -r scripts/requirements.txt

# News pre-fetch
python3 scripts/fetch_rss.py --type news
python3 scripts/fetch_openai_research.py --type news
python3 scripts/slim_inbox_for_synthesis.py --type news

# Culture pre-fetch (dry-run prompt)
python3 scripts/fetch_culture_research.py --dry-run --date 2026-06-10

# Email preview
python3 scripts/send_briefing_email.py --file briefings/news/2026-06-11.md --dry-run
```

## Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `news-prefetch.yml` | Daily 06:30 CET + manual | RSS → OpenAI → slim → commit `inbox/news/` |
| `berlin-culture-prefetch.yml` | Tuesday 06:00 CET + manual | Culture OpenAI → slim → commit `inbox/berlin-culture/` |
| `send-briefing-email.yml` | Push to `briefings/**/*.md` | Send styled email |

## Rollout checklist

- [x] Multi-briefing abstraction
- [ ] Update GitHub workflow files on `main` (rename daily → news-prefetch)
- [ ] Create second Cursor Automation for Berlin culture
- [ ] First manual Tuesday culture dry-run
- [ ] Verify both email subjects in inbox
