# Codex Cloud Synthesis PoC

Status: implementation prepared locally on `codex/pr-synthesis-cloud`.

This document describes the temporary PR-based synthesis architecture, how to connect the repository to Codex Cloud, how to run the first proof of concept, and how to remove the experiment cleanly if it does not work.

## Objective

Replace the API-billed synthesis step with a subscription-backed Codex Cloud task while keeping the briefing pipeline event-driven:

```text
pre-fetch writes inbox/** to main
    -> GitHub dispatches or receives the synthesis-request workflow
    -> request workflow creates a synthesis PR and comments @codex
    -> Codex Cloud writes briefings/** and state/** to the PR branch
    -> verification workflow passes
    -> GitHub auto-merges the PR
    -> merge push triggers send-briefing-email.yml
```

The pre-fetch research jobs still use the existing `OPENAI_API_KEY` where configured. This PoC changes only the synthesis agent.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Current production branch until this PoC is merged |
| `codex/pr-synthesis-cloud` | Implementation branch, commit `595b284` |
| `backup/api-synthesis-current` | Snapshot of the previous API-backed workflow |

The backup branch preserves the old push-triggered `synthesize-briefing.yml`. Do not delete it until the PoC has completed successfully.

## Files changed

### New production-path files

- `.github/workflows/request-codex-synthesis.yml`
  - Runs on direct pushes to `main` that touch `inbox/**`.
  - Also supports manual dispatch with a type and date.
  - Detects the eligible inbox item.
  - Creates an `automation/synthesis-*` branch and PR.
  - Adds the `@codex` task comment.
- `.github/workflows/verify-synthesis-pr.yml`
  - Runs when the Codex synthesis PR changes.
  - Requires the request marker to be removed.
  - Requires exactly one production briefing and a state update.
  - Runs the existing type-specific verification scripts.
  - Merges the PR after successful verification.
- `prompts/codex-cloud-synthesis-run.md`
  - Tells Codex Cloud how to read the request marker, synthesize, verify, commit, and push.

### Existing files changed

- The four pre-fetch workflows now explicitly dispatch the request workflow after their `GITHUB_TOKEN` push.
- `prefetch-health-check.yml` now dispatches a synthesis PR request for missing briefings.
- `synthesize-briefing.yml` is manual-only and remains an API-backed fallback.
- `AGENTS.md` and `README.md` describe the new path.
- `CURSOR_INSTRUCTIONS.md` contains the durable copy of the historical Cursor rules.

## Why both push and dispatch triggers exist

GitHub does not start another workflow from a push made with the default `GITHUB_TOKEN`. The pre-fetch jobs use that token, so each one explicitly dispatches `request-codex-synthesis.yml` after its push.

The request workflow also has a normal `push` trigger. This supports direct human or external-token pushes to `main` and preserves the intended event-driven behavior.

## Account setup: what you need to do

No new repository secret is required for Codex Cloud synthesis. The connection is an account-level GitHub authorization, not an `OPENAI_API_KEY` setting.

OpenAI's documented GitHub flow requires Codex Cloud to be set up for the repository, then allows Codex tasks to be started from pull-request comments. See the [Codex GitHub integration documentation](https://developers.openai.com/codex/integrations/github).

### Connect the repository

1. Open the Codex or ChatGPT app while signed in to the account that has the Codex subscription you want to use.
2. Open Codex settings. Look for the GitHub, Cloud, Repository, or Code review area; the exact label can vary by surface and rollout.
3. Choose the option to connect or set up Codex Cloud for a GitHub repository.
4. Authorize GitHub when prompted.
5. Select the repository containing this project.
6. Grant access to this repository. Prefer repository-only access rather than access to every repository.
7. In Codex settings, enable the repository's GitHub Code Review / Codex integration.
8. Confirm that the repository appears as connected and that Codex can receive an `@codex` mention on a pull request.

Success signal: the repository is listed as connected in Codex settings and the repository's Codex/Code Review setting is enabled.

### Check GitHub Actions permissions

In GitHub:

1. Open the repository.
2. Go to **Settings → Actions → General**.
3. Confirm that GitHub Actions are allowed to run.
4. Confirm that the workflow token can read and write repository contents and pull requests.
5. If GitHub presents an option named **Allow GitHub Actions to create and approve pull requests**, enable it.
6. Confirm that auto-merge is allowed for the repository if GitHub presents that setting.

Success signal: the repository allows an Action to create a PR and the PR can be merged by the workflow after checks pass.

### Existing secrets and variables

Keep these as they are:

- `OPENAI_API_KEY`: still used by pre-fetch research and the manual API fallback.
- `RESEND_API_KEY`: used for email delivery and failure alerts.
- `GOOGLE_MAPS_API_KEY`: used by restaurant verification.
- `BRIEFING_FROM_EMAIL` and `BRIEFING_TO_EMAIL`: existing Actions variables for email.

Do not add a ChatGPT password, session cookie, or subscription token to GitHub Secrets.

## First PoC test

Do not merge the implementation branch until the Codex/GitHub connection is ready.

### Agent-side preparation

The agent will:

1. Push `codex/pr-synthesis-cloud` to GitHub.
2. Open a PR from that branch to `main`.
3. Check that the workflow files are visible to GitHub Actions.
4. Help trigger one controlled synthesis request.

### User-side test

Use a type/date whose inbox already exists and whose production briefing does not yet exist. Start with `news`, because its verification path is comparatively straightforward.

1. Open the implementation PR in GitHub.
2. Confirm the changed workflow files are visible in the PR.
3. After the branch is available on GitHub, open **Actions → Request Codex Cloud synthesis → Run workflow**.
4. Enter `type_id=news`.
5. Enter the date of an existing `inbox/news/YYYY-MM-DD-synthesis.json` or `inbox/news/YYYY-MM-DD-raw.json` file with no matching production briefing.
6. Start the workflow.
7. Open the workflow log and confirm it creates a PR named like `automation: synthesize news YYYY-MM-DD`.
8. Open that new synthesis PR and confirm it contains a request marker under `.github/synthesis-requests/`.
9. Confirm the PR has a comment beginning with `@codex`.
10. Wait for the Codex GitHub integration to react. The exact reaction/comment may vary; the important signal is a Codex task associated with the PR.
11. Confirm Codex writes `briefings/news/YYYY-MM-DD.md` and updates `state/news/` on the PR branch.
12. Confirm Codex removes the request marker and pushes a commit to the PR branch.
13. Confirm **Verify Codex synthesis PR** runs and passes.
14. Confirm the PR auto-merges to `main`.
15. Confirm the merge triggers `send-briefing-email.yml` and that the email delivery log is updated.

### PoC success criteria

The PoC is successful only if all of these are true:

- No synthesis step uses `OPENAI_API_KEY`.
- The initial handoff happens immediately after the request workflow is dispatched or receives a push.
- Codex Cloud responds to the PR comment.
- Codex writes the briefing and state files to the PR branch.
- Verification blocks an incomplete or invalid PR.
- A valid PR merges automatically.
- The merge triggers email delivery exactly once.
- The API fallback remains available throughout the test.

## Troubleshooting

### No synthesis PR appears

Check the **Request Codex Cloud synthesis** workflow log.

- If it says no eligible inbox change, verify the requested inbox file exists.
- If it says the briefing already exists, choose a date without a production briefing.
- If `gh workflow run` fails, check the Actions permission and workflow file on `main`.

### The PR exists but Codex does not react

Check:

- The repository is connected in Codex settings.
- GitHub authorization was granted to the correct account.
- Codex Code Review / GitHub integration is enabled for this repository.
- The PR comment visibly contains `@codex`.
- The PR is in the connected repository and not a fork.

The documented Codex trigger is a pull-request mention. Automatic review settings are separate; the PoC relies on the explicit `@codex` comment.

### Codex reacts but cannot push

Check that Codex has write permission to repository branches. The synthesis PR branch is intentionally separate from `main`; Codex should never need direct write access to `main`.

### Verification fails while Codex is still working

This is expected for the initial marker-only PR. The verification workflow is designed to fail until the marker is removed and the production briefing exists. A later Codex commit should cause the verification workflow to run again.

### Verification passes but auto-merge fails

Check repository auto-merge settings, branch protection, required checks, and whether the workflow token is allowed to merge pull requests. The PR can be merged manually after the verification check passes.

### Email does not send

Check that the PR merged into `main`, that the merged diff contains `briefings/**/*.md`, and that `RESEND_API_KEY`, `BRIEFING_FROM_EMAIL`, and `BRIEFING_TO_EMAIL` are still configured.

## Rollback

If the PoC fails:

1. Stop creating new synthesis requests by disabling **Request Codex Cloud synthesis** in GitHub Actions.
2. Close any open `automation/synthesis-*` PRs.
3. Restore the API-backed workflow by switching to `backup/api-synthesis-current` or by reapplying its `synthesize-briefing.yml` and pre-fetch dispatch behavior.
4. Re-enable or manually run the API-backed synthesis workflow.
5. Keep the failed synthesis PR and Actions logs until the cause is understood.
6. Do not delete the backup branch until the original workflow has produced a successful briefing again.

Rollback does not require deleting briefing files. If a partial PR was merged, inspect the merge commit and use the existing verification and email-delivery recovery workflows.

## Cleanup after a successful PoC

Only after at least one complete run per important briefing type:

1. Decide whether the manual API fallback should remain as an emergency path.
2. If not, remove the API-backed workflow and the old CI-only synthesis prompt.
3. Delete obsolete `detect_synthesis_trigger.py` branches and tests only after confirming no health-check or manual recovery path uses them.
4. Remove the backup branch after the retention period you choose.
5. Remove old Cursor automation documentation only if the Cursor automation is definitely disabled.
6. Keep `AGENTS.md`, `CURSOR_INSTRUCTIONS.md`, the Codex Cloud prompt, and this runbook.
7. Update the README workflow table and this document to reflect the final architecture.

## Current state

At the time this runbook was created:

- The implementation exists locally on `codex/pr-synthesis-cloud`.
- The implementation is committed as `595b284`.
- The old API workflow is preserved locally as `backup/api-synthesis-current`.
- The implementation branch has not yet been merged into `main`.
- GitHub/Codex Cloud account setup has not yet been confirmed.
