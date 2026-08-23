# External scheduling (cron-job.org → GitHub Actions)

GitHub's built-in `schedule:` trigger is best-effort and can start workflows hours late. Pre-fetch and health-check workflows are **manual + external trigger only** — no `schedule:` in the YAML.

[cron-job.org](https://cron-job.org) is free (donation-supported) and fires HTTP requests on time in any timezone, including `Europe/Berlin` (handles CET/CEST automatically).

## Recommended schedule (Europe/Berlin)

| Job | When | Workflow |
|-----|------|----------|
| News pre-fetch | Daily **06:30** | `news-prefetch.yml` |
| Culture pre-fetch | Tuesday **06:00** | `berlin-culture-prefetch.yml` |
| Restaurants pre-fetch | Thursday **07:00** | `berlin-restaurants-prefetch.yml` |
| Music discovery pre-fetch | Friday **09:00** | `music-discovery-prefetch.yml` |
| Health check | Daily **11:00** | `prefetch-health-check.yml` (`profile: all`) |

**Music discovery** materializes taste-cache into `inbox/`, then runs OpenAI web_search for Bandcamp/YouTube/cover candidates (same spend-cap pattern as culture/restaurants). See `docs/music-discovery-bridge.md`.

**Health check timing:** One job at 11:00 Berlin covers all types. On a prefetch day (e.g. Tuesday culture at 06:00), the 11:00 run is the primary check that the inbox landed (~5 hours later) **and** that a production briefing exists. On other days, the same job re-checks the current week's culture/restaurant inbox keys as a backup — not the main alert path.

## 1. GitHub token

### cron-job.org (production trigger)

Store the token in cron-job.org only — see headers in section 3.

### Local testing (optional)

Add to `.env` (gitignored — never commit):

```bash
cp .env.example .env
# Edit .env:
GITHUB_TOKEN=github_pat_...
```

Load before curl:

```bash
set -a && source .env && set +a
```

**Create the token:**

1. [github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta) → fine-grained PAT
2. Repository: **`inigober/briefings`**
3. **Actions: Read and write** (Read-only causes HTTP 403)
4. Or classic PAT with **`repo`** scope

### Token expiry

| Source | What happens |
|--------|----------------|
| **GitHub** | Email as expiry approaches |
| **cron-job.org** | Failure notification on **403** after expiry |

Enable cron-job.org **Notifications → on failure** on at least the news job.

## 2. cron-job.org setup

1. [console.cron-job.org/signup](https://console.cron-job.org/signup)
2. Create each job via **Import from cURL** or manually
3. Set **Timezone: Europe/Berlin** and the schedule from the table above
4. **Run now** → expect **HTTP 204**

## 3. Shared headers (every job)

| Header | Value |
|--------|--------|
| `Accept` | `application/vnd.github+json` |
| `Authorization` | `Bearer YOUR_GITHUB_TOKEN` |
| `Content-Type` | `application/json` |
| `X-GitHub-Api-Version` | `2022-11-28` |

## 4. cURL commands (import into cron-job.org)

### News pre-fetch — daily 06:30

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/news-prefetch.yml/dispatches
```

### Culture pre-fetch — Tuesday 10:00

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/berlin-culture-prefetch.yml/dispatches
```

### Restaurants pre-fetch — Thursday 10:00

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/berlin-restaurants-prefetch.yml/dispatches
```

### Music discovery pre-fetch — Friday 09:00

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/music-discovery-prefetch.yml/dispatches
```

### Health check — daily 11:00 (all types scheduled today)

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main","inputs":{"profile":"all"}}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/prefetch-health-check.yml/dispatches
```

### Local test with `.env`

```bash
set -a && source .env && set +a

curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/news-prefetch.yml/dispatches
```

Success = **HTTP 204**.

## 5. Verify end-to-end

1. Pre-fetch run → green in [Actions](https://github.com/inigober/briefings/actions)
2. `inbox/{type}/` commit on `main`
3. Cursor Automation **Briefing synthesis** runs on that push
4. `briefings/{type}/` commit → email workflow sends

**Duplicate pre-fetch same day:** If a briefing file already exists for that date, synthesis **skips** (guard in `detect_synthesis_trigger.py`). Test briefings must use `YYYY-MM-DD.test.md` so they never block production (see README **End-to-end testing**).

## Troubleshooting

### HTTP 403 — Resource not accessible by personal access token

Response header `x-accepted-github-permissions: actions=write` → token needs **Actions: Read and write**, not Read-only.

### HTTP 401

Token expired or wrong `Authorization` header.

### Synthesis ran twice

Each `inbox/` push should trigger **one** Cursor Automation run. Two synthesis runs = two pre-fetch commits (e.g. morning schedule + afternoon test), or a leftover second automation. Check [git log for `inbox/` commits](https://github.com/inigober/briefings/commits/main). Keep only one enabled “Briefing synthesis” automation.

### Inbox landed but no briefing

Pre-fetch committed `inbox/{type}/` but `briefings/{type}/YYYY-MM-DD.md` never appeared. The 11:00 health check emails this separately and does **not** retry pre-fetch (that would waste OpenAI spend). **Fix:** enable or re-run **Briefing synthesis** at [cursor.com/automations](https://cursor.com/automations), or re-run the matching `*-prefetch.yml` so a fresh inbox push retriggers Cursor.

### Workflow runs but no inbox commit

Open the Actions log — likely OpenAI spend cap or script error.

### Job cancelled — "not acquired by Runner of type hosted"

GitHub could not assign a hosted runner within ~15 minutes (queue saturation). The pre-fetch script never ran. **Fix:** re-run the workflow manually (Actions → workflow → **Run workflow**) or wait for the 11:00 health check, which re-dispatches missed pre-fetches automatically.
