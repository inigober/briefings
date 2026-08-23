# Codex Cloud PR — briefing synthesis

Runnable instructions for the Codex Cloud GitHub synthesis PR workflow.

## Hard constraints

1. Read `.github/synthesis-requests/*.json` and use its `type_id`, `date`, and `matched_files` values.
2. Read the matching `prompts/{type_id}/synthesis-run.md` and follow its editorial and state-update rules.
3. Skip the type prompt's Step 0 push guard; this PR is already the routed synthesis job.
4. Do not browse or perform open-ended research. Use the inbox, state, configuration, and repository instructions only.
5. Do not use the OpenAI API. This task is running through the connected Codex Cloud GitHub integration.
6. Write the production file `briefings/{type_id}/{date}.md` and update the required `state/{type_id}/` files.

## Verification and publish

Before finishing:

- Run the required type-specific verification commands from the applicable synthesis prompt.
- Confirm exactly one production briefing and the expected state updates exist.
- Remove the matching `.github/synthesis-requests/{type_id}-{date}.json` marker only after the briefing and state updates are complete.
- Commit all changes to the current `automation/synthesis-*` branch with message `briefing/{type_id}: {date}`.
- Push the current PR branch so GitHub can run `verify-synthesis-pr.yml`.

Do not push to `main`. Do not send email. The verified PR merge produces the `main` push that triggers email delivery.
