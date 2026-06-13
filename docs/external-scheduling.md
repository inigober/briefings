# External scheduling (cron-job.org → GitHub Actions)

GitHub's built-in `schedule:` trigger is best-effort and can start workflows hours late. Pre-fetch and health-check workflows are **manual + external trigger only** — no `schedule:` in the YAML.

[cron-job.org](https://cron-job.org) is free (donation-supported) and fires HTTP requests on time in any timezone, including `Europe/Berlin` (handles CET/CEST automatically).

## 1. Create a GitHub token

1. Go to [https://github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta)
2. **Generate new token** → fine-grained personal access token
3. **Repository access:** Only select repositories → `inigober/briefings`
4. **Permissions → Repository permissions:**
   - **Actions:** Read and write
   - **Contents:** Read-only
   - **Metadata:** Read-only (usually auto-granted)
5. Generate and **copy the token** — you won't see it again

**If you get HTTP 403**, use a **classic** token instead (often simpler for private repos):

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)**
2. Scope: **`repo`** (full control of private repositories)
3. Use the same `Authorization: Bearer …` header in cron-job.org

Store the token only in cron-job.org (or your password manager). Never commit it to the repo.

### Token expiry — will you get an alert?

| Source | What happens |
|--------|----------------|
| **GitHub** | Sends an email to your account as the token nears expiry (GitHub does not publish the exact lead time — treat it as a heads-up, not a guarantee) |
| **cron-job.org** | If you enable **Notifications → on failure**, a expired/revoked token causes **403** on the next scheduled run and cron-job.org emails you |
| **Health-check email** | Does **not** detect a dead cron token — it only checks whether inbox files landed |

**Recommendation:** Enable cron-job.org failure notifications on the news pre-fetch job, and put a calendar reminder ~2 weeks before the token expiry date shown when you created it.

## 2. Create a cron-job.org account

1. Go to [https://console.cron-job.org/signup](https://console.cron-job.org/signup)
2. Sign up and verify email
3. Open [https://console.cron-job.org/jobs/create](https://console.cron-job.org/jobs/create)

## 3. Shared HTTP settings (all jobs)

Every job uses the same request shape; only the URL, schedule, and body differ.

| Field | Value |
|-------|--------|
| Request method | **POST** |
| Request timeout | 30 seconds (default is fine) |

**Headers** (add each one):

| Header | Value |
|--------|--------|
| `Accept` | `application/vnd.github+json` |
| `Authorization` | `Bearer YOUR_GITHUB_TOKEN` |
| `Content-Type` | `application/json` |
| `X-GitHub-Api-Version` | `2022-11-28` |

**Body type:** JSON

## 4. Jobs to create

Create **five** separate cron jobs. After saving each one, click **Run now** and confirm the matching workflow appears under [GitHub Actions](https://github.com/inigober/briefings/actions).

### Job A — News pre-fetch (daily)

| Setting | Value |
|---------|--------|
| Title | `briefings — news pre-fetch` |
| URL | `https://api.github.com/repos/inigober/briefings/actions/workflows/news-prefetch.yml/dispatches` |
| Schedule | Every day at **06:30** (or any time you prefer) |
| Timezone | **Europe/Berlin** |

Body:

```json
{"ref":"main"}
```

### Job B — Berlin culture pre-fetch (Tuesday)

| Setting | Value |
|---------|--------|
| Title | `briefings — culture pre-fetch` |
| URL | `https://api.github.com/repos/inigober/briefings/actions/workflows/berlin-culture-prefetch.yml/dispatches` |
| Schedule | Every **Tuesday** at **06:00** |
| Timezone | **Europe/Berlin** |

Body:

```json
{"ref":"main"}
```

### Job C — Berlin restaurants pre-fetch (Thursday)

| Setting | Value |
|---------|--------|
| Title | `briefings — restaurants pre-fetch` |
| URL | `https://api.github.com/repos/inigober/briefings/actions/workflows/berlin-restaurants-prefetch.yml/dispatches` |
| Schedule | Every **Thursday** at **07:00** |
| Timezone | **Europe/Berlin** |

Body:

```json
{"ref":"main"}
```

### Job D — Pre-fetch health check, morning (daily)

Runs ~90 minutes after news pre-fetch (e.g. **08:00** if pre-fetch is 06:30).

| Setting | Value |
|---------|--------|
| Title | `briefings — health check (morning)` |
| URL | `https://api.github.com/repos/inigober/briefings/actions/workflows/prefetch-health-check.yml/dispatches` |
| Schedule | Every day at **08:00** |
| Timezone | **Europe/Berlin** |

Body:

```json
{"ref":"main","inputs":{"profile":"morning"}}
```

### Job E — Pre-fetch health check, restaurants (Thursday)

| Setting | Value |
|---------|--------|
| Title | `briefings — health check (restaurants)` |
| URL | `https://api.github.com/repos/inigober/briefings/actions/workflows/prefetch-health-check.yml/dispatches` |
| Schedule | Every **Thursday** at **09:05** |
| Timezone | **Europe/Berlin** |

Body:

```json
{"ref":"main","inputs":{"profile":"restaurants"}}
```

## 5. Enable failure notifications (recommended)

In cron-job.org → job → **Notifications**: turn on email when a job fails (HTTP non-2xx). This catches expired tokens (**403**), wrong permissions, and bad URLs — not just OpenAI failures inside the workflow.

## 6. Verify

1. **Run now** on Job A (news pre-fetch)
2. Within ~1 minute, [Actions → News research pre-fetch](https://github.com/inigober/briefings/actions/workflows/news-prefetch.yml) should show a new run triggered by your GitHub user (workflow_dispatch)
3. When the run finishes, `main` should have a commit like `inbox/news: YYYY-MM-DD research pre-fetch`
4. That push triggers the **Briefing synthesis** Cursor automation

## Troubleshooting

### HTTP 403 Forbidden

Open the failed run in cron-job.org → **History** → click the execution → read the **response body**. GitHub returns a JSON `message` field that narrows it down.

| Response message | Fix |
|------------------|-----|
| `Must have admin rights to Repository` | Usually a **malformed request**, not missing admin. Check: POST method, JSON body `{"ref":"main"}`, `Content-Type: application/json`, token in `Authorization: Bearer …` |
| `Resource not accessible by personal access token` | Token lacks permission — regenerate with **Actions: Read and write** (fine-grained) or **`repo`** scope (classic) |
| `Not Found` | Wrong repo name or workflow filename in URL |
| (empty / rate limit) | Wait and retry; check `X-RateLimit-Remaining` if testing with curl |

**Checklist (most 403s are one of these):**

1. **Token type:** Try **classic PAT** with **`repo`** scope if fine-grained keeps failing
2. **Repository access:** Fine-grained token must explicitly include `inigober/briefings`
3. **Body:** cron-job.org body type must be **JSON**, not form data — exactly `{"ref":"main"}`
4. **Headers:** All four headers from section 3; no extra spaces in the token
5. **Actions enabled:** Repo → **Settings → Actions → General** → allow actions
6. **Branch:** `ref` must be `main` (your default branch)

**Test from your Mac** (paste token locally, never commit):

```bash
curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/inigober/briefings/actions/workflows/news-prefetch.yml/dispatches
```

Success = **HTTP 204** with an empty body. If curl works but cron-job.org fails, compare headers/body in cron-job.org's job editor.

### Other errors

| Symptom | Fix |
|---------|-----|
| HTTP 401 | Token expired or wrong value in `Authorization` header |
| HTTP 404 | Check workflow filename in URL (must match `.github/workflows/*.yml`) |
| HTTP 422 | Body must be valid JSON; include `"ref":"main"` |
| Workflow runs but no inbox commit | Open the run log — likely OpenAI spend cap or script error |
| cron-job.org shows 204 / empty response | Normal — GitHub returns 204 No Content on success |

## curl reference (manual test)

Replace `YOUR_GITHUB_TOKEN`:

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/inigober/briefings/actions/workflows/news-prefetch.yml/dispatches \
  -d '{"ref":"main"}'
```
