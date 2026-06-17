# Personal Briefings

Repo-based briefing platform: **news** (daily), **Berlin culture** (weekly Tuesday), and **Berlin restaurants** (weekly Thursday). Novelty-first editorial, automated pre-fetch, Cursor cloud synthesis, Resend email.

## Architecture

```
config/briefings.yaml          ← registry (paths, schedules, prompts)
        ↓
┌───────────────────────────────────────────────────────────────┐
│ news (daily)                                                  │
│   RSS + WordPress → inbox/news/ → synthesis → briefings/news/ │
├───────────────────────────────────────────────────────────────┤
│ berlin-culture (Tuesday)                                      │
│   RSS + WordPress + OpenAI (web_search) → verify URLs → slim │
├───────────────────────────────────────────────────────────────┤
│ berlin-restaurants (Thursday)                                 │
│   OpenAI → Places verify → slim → briefings/…                │
└───────────────────────────────────────────────────────────────┘
        ↓
GitHub Action on push → styled HTML email (Resend, same recipient)
```

| Layer | Responsibility |
|-------|----------------|
| `config/briefings.yaml` | Briefing type registry |
| `config/briefings/{type}/` | Topics, sources per type |
| Pre-fetch scripts | Research → typed `inbox/` |
| **One** Cursor Automation (dispatcher) | Routes push → correct synthesis |
| `scripts/detect_synthesis_trigger.py` | Testable routing logic |
| `scripts/send_briefing_email.py` | Markdown → HTML → inbox |

## Repository layout

```
├── config/
│   ├── briefings.yaml                 # type registry
│   └── briefings/{type}/              # topics.yaml, sources.yaml
├── .cursor/rules/                       # editorial rules per type
├── prompts/
│   ├── cursor-automation-synthesis.md   # single automation setup
│   ├── synthesis-dispatcher-run.md      # dispatcher steps
│   └── {type}/synthesis-run.md          # per-type synthesis steps
├── inbox/{type}/                        # pre-fetch JSON
├── briefings/{type}/                    # committed outputs
├── state/{type}/                        # dedup / memory
└── scripts/
    ├── detect_synthesis_trigger.py
    ├── briefing_paths.py
    └── fetch_*.py, slim_inbox_for_synthesis.py, send_briefing_email.py
```

## For PMs (learning as you go)

| You care about | File / place |
|----------------|--------------|
| Which briefings exist | `config/briefings.yaml` |
| Editorial rules | `.cursor/rules/{type}-briefing-style.mdc` |
| Topics & sources | `config/briefings/{type}/` |
| Synthesis steps (per type) | `prompts/{type}/synthesis-run.md` |
| Synthesis dispatcher | `prompts/synthesis-dispatcher-run.md` |
| Trigger routing (testable) | `scripts/detect_synthesis_trigger.py` |
| Pre-fetch schedules | `docs/external-scheduling.md` (cron-job.org → GitHub Actions) |
| OpenAI pre-fetch spend cap | `scripts/openai_spend.py`, `OPENAI_DAILY_SPEND_CAP_USD` |
| Email delivery | `.github/workflows/send-briefing-email.yml` |

## Briefing types

### News Briefing (daily)

Sections: Spain, Germany, Berlin, World, Other Headlines Today, What Matters Today, Selected Reads.

Title: `# News Briefing — DD Month YYYY`

### Berlin Culture Briefing (weekly, Tuesday)

Sections: Top Picks, Exhibitions, Film, Performing Arts, Music, Wildcards, Advance Radar (optional).

Title: `# Berlin Culture Briefing — Week of June 16–22, 2026`

### Berlin Restaurant Briefing (weekly, Thursday)

Sections: restaurant entries + This week's strongest bets.

Title: `# Berlin Restaurant Briefing — Week of YYYY-MM-DD`

## Setup

### GitHub secrets and variables

**Secrets:** `OPENAI_API_KEY`, `RESEND_API_KEY`, `GOOGLE_MAPS_API_KEY` (restaurant pre-fetch Places verification)

**Variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_RESEARCH_MODEL` | `gpt-4.1` | Pre-fetch model |
| `OPENAI_DAILY_SPEND_CAP_USD` | `2` (built-in default) | Hard daily cap for OpenAI pre-fetch. **Optional** — only add this variable if you want a value other than $2; no code change needed. |
| `BRIEFING_FROM_EMAIL` | — | Resend sender (briefing email + spend-cap alerts) |
| `BRIEFING_TO_EMAIL` | — | Recipient |

All briefing types email the **same recipient**; subjects are each briefing's H1 title prefixed with a type emoji (`📰` news, `🎭` culture, `🍽️` restaurants — set in `config/briefings.yaml`).

### OpenAI pre-fetch spend cap

Pre-fetch scripts track **estimated** daily OpenAI spend and **abort** when the cap is reached.

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

Create **one** automation in [Cursor Automations](https://cursor.com/automations):

| Automation | Setup guide |
|------------|-------------|
| Briefing synthesis dispatcher | `prompts/cursor-automation-synthesis.md` |

- Trigger: push to `main`
- Runtime: cloud agent
- Paste the short pointer block from the setup guide once

The dispatcher runs `scripts/detect_synthesis_trigger.py` to decide which briefing type (if any) should synthesize, then executes that type's `prompts/{type}/synthesis-run.md` steps 1–4.

**Push-only by design.** Synthesis runs when pre-fetch commits to `inbox/` and triggers a push. There is no scheduled synthesis cron in Cursor or GitHub Actions.

**Optional backup (not wired):** The same script supports `--backup`, which scans the repo for "inbox ready but briefing file missing" (prefetch succeeded, synthesis never ran). It is tested but nothing calls it in production — recovery today is manual (re-run the Cursor automation or synthesis steps). To automate later, you could add a cron-job.org job that runs the script and triggers synthesis when it returns a type; see `detect_backup_trigger()` in `scripts/detect_synthesis_trigger.py`.

**Disable** any legacy per-type push automations (news, berlin-culture, berlin-restaurants) after the dispatcher is live.

Test routing locally:

```bash
python scripts/detect_synthesis_trigger.py --json
```

### Schedules

Pre-fetch and health-check workflows have **no GitHub `schedule:` trigger** — GitHub's built-in cron is best-effort and can start hours late. Instead, [cron-job.org](https://cron-job.org) (free) POSTs to `workflow_dispatch` at fixed **Europe/Berlin** times.

**Setup:** `docs/external-scheduling.md`

| Job (cron-job.org) | Local time (Europe/Berlin) | GitHub workflow |
|--------------------|----------------------------|-----------------|
| News pre-fetch | Daily **06:30** | `news-prefetch.yml` |
| Culture pre-fetch | Tuesday **06:00** | `berlin-culture-prefetch.yml` |
| Restaurants pre-fetch | Thursday **07:00** | `berlin-restaurants-prefetch.yml` |
| Health check | Daily **11:00** | `prefetch-health-check.yml` (`profile: all`) |

Synthesis is **push-triggered** via the **Briefing synthesis** Cursor automation when pre-fetch commits to `inbox/`. If pre-fetch failed, recover from health-check emails or re-run the matching `*-prefetch.yml` workflow. If pre-fetch succeeded but no briefing appeared, re-run the Cursor automation manually (`--backup` detection exists in the script but is not scheduled — see **Cursor Automations** above).

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

### End-to-end testing

When you run a full synthesis test and commit the result, **never** use the production filename `briefings/{type}/YYYY-MM-DD.md` for a future scheduled date. That file blocks real synthesis on the live day (push guard + email workflow).

| Purpose | Filename | Commits to `main`? | Blocks production? | Auto-email? |
|---------|----------|-------------------|--------------------|-------------|
| **Production run** | `YYYY-MM-DD.md` | Yes | — | Yes |
| **End-to-end test** | `YYYY-MM-DD.test.md` | Optional | No | No |
| **Pre-fetch only** | `inbox/{type}/…` | Yes | No | No |

**Rules:**

1. Test briefings → `briefings/{type}/YYYY-MM-DD.test.md` (same date key as inbox is fine).
2. Commit message for tests → include `end-to-end test` and **do not** use the `inbox/{type}:` prefix unless you intend to trigger synthesis.
3. Prefer `fetch_* --dry-run` and `send_briefing_email.py --dry-run` when you only need to validate scripts locally without touching git.

### Manual test

```bash
pip install -r scripts/requirements.txt

# News pre-fetch
python3 scripts/fetch_rss.py --type news
python3 scripts/fetch_wordpress.py --type news
python3 scripts/merge_news_inbox.py --type news
python3 scripts/verify_news_urls.py --type news
python3 scripts/slim_inbox_for_synthesis.py --type news

# After writing a briefing (synthesis agent)
python3 scripts/verify_briefing_sources.py --type news --date YYYY-MM-DD

# Culture pre-fetch (dry-run prompt)
python3 scripts/fetch_culture_research.py --dry-run --date 2026-06-10

# Restaurant Places verification + slim (after pre-fetch)
python3 scripts/verify_restaurant_maps.py --date 2026-06-18
python3 scripts/slim_inbox_for_synthesis.py --type berlin-restaurants --date 2026-06-18

# Trigger routing (after a pre-fetch commit)
python3 scripts/detect_synthesis_trigger.py --json

# Pre-fetch health check (dry-run — no email)
python3 scripts/check_prefetch_health.py --dry-run

# Email preview
python3 scripts/send_briefing_email.py --file briefings/news/2026-06-11.md --dry-run

# Unit tests
python3 -m unittest discover -s tests -v
```

## Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `test.yml` | push / PR to `main` | `python -m unittest discover -s tests` |
| `news-prefetch.yml` | cron-job.org daily 06:30 Berlin + manual | RSS → WordPress → merge → verify URLs → slim → commit `inbox/news/` |
| `verify-briefing-sources.yml` | push to `briefings/news/` + manual | Ensures footnote URLs exist in synthesis inbox |
| `berlin-culture-prefetch.yml` | cron-job.org Tue 06:00 Berlin + manual | RSS + WordPress + OpenAI → verify URLs → slim → commit `inbox/berlin-culture/` |
| `berlin-restaurants-prefetch.yml` | cron-job.org Thu 07:00 Berlin + manual | OpenAI → Places verify → slim → commit `inbox/berlin-restaurants/` |
| `prefetch-health-check.yml` | cron-job.org daily 11:00 Berlin | Email if inbox missing or slim incomplete (Resend) |
| `send-briefing-email.yml` | Push to `briefings/**/*.md` | Verify news sources, then send styled email (newest per type by default) |

Pre-fetch workflows use **concurrency groups** so overlapping manual + scheduled runs queue instead of racing. The email workflow sends only the **newest dated briefing per type** when a push changes multiple files; use workflow dispatch with **all_changed** or `--all-changed` to replay every file.

## Rollout checklist

- [x] Multi-briefing abstraction (news, berlin-culture, berlin-restaurants)
- [x] Single synthesis dispatcher + `detect_synthesis_trigger.py`
- [x] External scheduling via cron-job.org (see `docs/external-scheduling.md`)
- [x] Push-only **Briefing synthesis** Cursor automation (no backup schedule crons)
- [ ] Configure four cron-job.org jobs (see `docs/external-scheduling.md`)
- [ ] Disable three legacy per-type Cursor automations if still enabled
- [ ] Verify one full cycle per briefing type (prefetch → synthesis → email)
- [ ] Confirm email sends only the intended briefing on normal pushes
