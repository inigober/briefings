@AGENTS.md

# Claude-specific notes

## Where things live

- Editorial rules per type: `config/briefings/{type}/style-rules.md` (registry key `style_rule` in `config/briefings.yaml`).
- Synthesis steps per type: `prompts/{type}/synthesis-run.md`; routing: `prompts/synthesis-dispatcher-run.md`.
- Trigger routing logic (testable): `scripts/detect_synthesis_trigger.py`.
- Run the tests with `python3 -m pytest -q tests` (install once with `pip install -r requirements-dev.txt`). Do not use `unittest discover`: it silently skips plain `def test_...()` functions.

## Working with the project owner

The owner is a PM learning technical skills, not a software engineer. Optimize for clarity over brevity when explaining changes.

- For every change explain **what** changed and **why**, and name the file that controls it. Define jargon on first use in a session. No forced analogies to unrelated business concepts.
- Do the work yourself where tools allow (edits, tests, dry-runs, `gh` commands). Ask before destructive or credential-handling actions.
- End task-oriented replies with **What I can do (agent)** and **What you need to do (your side)**. For user steps give numbered instructions: exact URL or menu, what to enter, what success looks like, one common fix.
- Tone: patient and direct; no "simply", "just", "obviously". Match depth to the task.

## Safety rules for this repo

- `briefings/{type}/YYYY-MM-DD.md` is the production filename and triggers the email. For tests use `YYYY-MM-DD.test.md` (see README, "End-to-end testing").
- Never commit `.env`. Secrets live in GitHub Actions secrets.
- Pushes to `main` affect the live automated pipeline; confirm with the owner before pushing changes to workflows, prompts, or scripts.

## Repo hygiene (interactive sessions only)

The owner wants the repo kept clean and to be told about loose ends. This section does **not** apply to the CI synthesis agent, which must not run git (see AGENTS.md).

- At the end of any task that touched git, report: unmerged branches with work not on `main`, open pull requests, and temporary files or workflows still in place. Say "nothing unmerged, no open PRs" when that is the case.
- Remove temporary helpers (probe workflows, test files) before merging, and say so.
- After a feature branch is merged, say whether its remote branch can be deleted. Delete branches only with the owner's OK.
- Note: `main` history was restarted on 2026-10-30, so `git log main..branch` misreports branches older than that. Compare file contents instead.
