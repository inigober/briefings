#!/usr/bin/env python3
"""Decide which briefing synthesis (if any) should run for a git commit.

Used by the single Cursor synthesis dispatcher automation. Logic mirrors Step 0
in each prompts/*/synthesis-run.md push guard.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing_paths import (
    REPO_ROOT,
    load_briefing_type,
    load_manifest,
    production_briefing_exists,
)
from cron_schedule import is_scheduled_on_date
from prefetch_dates import resolve_inbox_date_key

RESEARCH_SUFFIXES = ("-synthesis.json", "-raw.json", "-context.json")
IGNORED_INBOX_SUFFIXES = (
    "-rss.json",
    "-wordpress.json",
    "-spend.json",
    "-spend-cap.error.txt",
    "-taste-snapshot.md",  # companion to -context.json; not a separate trigger
)
INBOX_COMMIT_PREFIX = "inbox/"
BRIEFING_EXISTS_SKIP_HOURS = 24


@dataclass(frozen=True)
class TriggerDecision:
    type_id: str | None
    reason: str
    commit_sha: str
    commit_subject: str
    matched_files: tuple[str, ...]

    def to_json(self) -> dict:
        return {
            "type_id": self.type_id,
            "reason": self.reason,
            "commit_sha": self.commit_sha,
            "commit_subject": self.commit_subject,
            "matched_files": list(self.matched_files),
        }


def _run_git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def resolve_commit_sha(explicit: str | None) -> str:
    if explicit:
        return _run_git("rev-parse", explicit)
    return _run_git("rev-parse", "HEAD")


def commit_subject(sha: str) -> str:
    return _run_git("log", "-1", "--format=%s", sha)


def changed_files_in_commit(sha: str) -> list[str]:
    parent = _run_git("rev-parse", f"{sha}^")
    if not parent:
        return []
    try:
        _run_git("cat-file", "-e", f"{parent}^{{commit}}")
    except subprocess.CalledProcessError:
        return []
    out = _run_git("diff", "--name-only", parent, sha)
    return [line for line in out.splitlines() if line.strip()]


def is_research_inbox_file(path: str, inbox_prefix: str) -> bool:
    if not path.startswith(inbox_prefix + "/"):
        return False
    name = Path(path).name
    if name == ".gitkeep":
        return False
    if any(name.endswith(suffix) for suffix in IGNORED_INBOX_SUFFIXES):
        return False
    return any(name.endswith(suffix) for suffix in RESEARCH_SUFFIXES)


def research_date_from_path(path: str) -> str | None:
    name = Path(path).name
    for suffix in RESEARCH_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def synthesis_file_modified(paths: list[str], inbox_prefix: str, date_str: str) -> bool:
    target = f"{inbox_prefix}/{date_str}-synthesis.json"
    return target in paths


def built_at_within_hours(path: Path, hours: int) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    built_at = data.get("built_at")
    if not built_at:
        return False
    try:
        built = datetime.fromisoformat(str(built_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if built.tzinfo is None:
        built = built.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return built >= cutoff


def evaluate_type(
    type_id: str,
    *,
    commit_sha: str,
    subject: str,
    changed: list[str],
) -> tuple[bool, str, tuple[str, ...]]:
    bt = load_briefing_type(type_id)
    inbox_rel = str(bt.inbox_dir.relative_to(REPO_ROOT)).replace("\\", "/")
    research_files = [p for p in changed if is_research_inbox_file(p, inbox_rel)]

    if not research_files:
        return False, f"No {type_id} inbox research in commit", ()

    commit_prefix = f"{INBOX_COMMIT_PREFIX}{type_id}:"
    if subject.startswith(commit_prefix):
        fresh_reason = "commit message matches pre-fetch prefix"
    else:
        fresh = False
        for path in research_files:
            if path.endswith("-synthesis.json") or path.endswith("-context.json"):
                full = REPO_ROOT / path
                if built_at_within_hours(full, BRIEFING_EXISTS_SKIP_HOURS):
                    fresh = True
                    break
        if not fresh:
            return (
                False,
                f"Inbox changed but not a fresh pre-fetch for {type_id}",
                tuple(research_files),
            )
        fresh_reason = "inbox payload built_at within 24h"

    for path in research_files:
        date_str = research_date_from_path(path)
        if not date_str:
            continue
        if production_briefing_exists(bt, date_str):
            return (
                False,
                f"Briefing already exists for {date_str}",
                tuple(research_files),
            )

    return True, fresh_reason, tuple(research_files)


def _type_priority(type_id: str) -> int:
    order = {
        tid: idx
        for idx, tid in enumerate(
            ("news", "berlin-culture", "berlin-restaurants", "music-discovery")
        )
    }
    return order.get(type_id, 99)


def detect_backup_trigger(date_str: str | None = None) -> TriggerDecision:
    """Find inbox research waiting for synthesis (cron backup path)."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candidates: list[tuple[str, str, tuple[str, ...]]] = []

    for type_id in load_manifest():
        bt = load_briefing_type(type_id)
        inbox_date = resolve_inbox_date_key(type_id, date_str)

        synthesis_path = bt.inbox_path(inbox_date, "synthesis")
        raw_path = bt.inbox_path(inbox_date, "raw")
        context_path = bt.inbox_dir / f"{inbox_date}-context.json"
        inbox_files: list[str] = []
        if type_id == "music-discovery":
            if context_path.exists():
                inbox_files.append(str(context_path.relative_to(REPO_ROOT)))
            else:
                continue
        elif synthesis_path.exists():
            inbox_files.append(str(synthesis_path.relative_to(REPO_ROOT)))
        elif raw_path.exists():
            inbox_files.append(str(raw_path.relative_to(REPO_ROOT)))
        else:
            continue

        if production_briefing_exists(bt, inbox_date):
            continue

        candidates.append(
            (
                type_id,
                f"backup: inbox ready for {inbox_date}, briefing missing",
                tuple(inbox_files),
            )
        )

    if not candidates:
        return TriggerDecision(
            type_id=None,
            reason=f"No unprocessed inbox for {date_str}",
            commit_sha="",
            commit_subject="(backup cron)",
            matched_files=(),
        )

    type_id, reason, matched = sorted(candidates, key=lambda item: _type_priority(item[0]))[0]
    return TriggerDecision(
        type_id=type_id,
        reason=reason,
        commit_sha="",
        commit_subject="(backup cron)",
        matched_files=matched,
    )


def _skip_rejection_priority(reason: str) -> int:
    if reason.startswith("Briefing already exists"):
        return 0
    if reason.startswith("Inbox changed but not a fresh pre-fetch"):
        return 1
    return 2


def _best_skip_rejection(
    rejections: list[tuple[str, str, tuple[str, ...]]],
) -> tuple[str, tuple[str, ...]] | None:
    """Pick the most informative near-miss from per-type evaluation."""
    if not rejections:
        return None
    type_id, reason, matched = sorted(
        rejections,
        key=lambda item: (_skip_rejection_priority(item[1]), _type_priority(item[0])),
    )[0]
    return f"{type_id}: {reason}", matched


def detect_trigger(commit_sha: str | None = None, *, backup: bool = False) -> TriggerDecision:
    if backup:
        return detect_backup_trigger()
    sha = resolve_commit_sha(commit_sha)
    subject = commit_subject(sha)
    changed = changed_files_in_commit(sha)

    rejections: list[tuple[str, str, tuple[str, ...]]] = []
    for type_id in sorted(load_manifest()):
        should_run, reason, matched = evaluate_type(
            type_id, commit_sha=sha, subject=subject, changed=changed
        )
        if should_run:
            return TriggerDecision(
                type_id=type_id,
                reason=reason,
                commit_sha=sha,
                commit_subject=subject,
                matched_files=matched,
            )
        if matched:
            rejections.append((type_id, reason, matched))

    if not changed:
        return TriggerDecision(
            type_id=None,
            reason="No changed files in commit (or no parent)",
            commit_sha=sha,
            commit_subject=subject,
            matched_files=(),
        )

    skip = _best_skip_rejection(rejections)
    if skip:
        reason, matched = skip
        return TriggerDecision(
            type_id=None,
            reason=reason,
            commit_sha=sha,
            commit_subject=subject,
            matched_files=matched,
        )

    return TriggerDecision(
        type_id=None,
        reason="No briefing type matched fresh inbox research in this commit",
        commit_sha=sha,
        commit_subject=subject,
        matched_files=(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect which briefing synthesis should run for a commit"
    )
    parser.add_argument(
        "--commit",
        help="Commit SHA to inspect (default: HEAD)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of type id or 'skip'",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Cron backup: inbox exists for today but briefing is missing",
    )
    args = parser.parse_args()

    try:
        decision = detect_trigger(args.commit, backup=args.backup)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(decision.to_json(), indent=2))
        return 0

    if decision.type_id:
        print(decision.type_id)
        return 0

    print("skip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
