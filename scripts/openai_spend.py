#!/usr/bin/env python3
"""Daily OpenAI spend tracking, estimation, and hard cap for pre-fetch scripts."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Conservative per-section reservation so parallel workers do not overshoot the cap.
SECTION_BUDGET_RESERVE_USD = 0.55
# Single combined OpenAI call (restaurants) — actual cost ~$0.06–0.15.
COMBINED_FETCH_BUDGET_RESERVE_USD = 0.15
# Culture: search phase (required web_search) + JSON structure phase — ~$0.08–0.30.
CULTURE_FETCH_BUDGET_RESERVE_USD = 0.30

# Web search tool: $10 / 1k calls (OpenAI pricing page, 2026).
WEB_SEARCH_COST_PER_CALL_USD = 0.01

# Token rates per 1M tokens: (input, cached_input, output)
MODEL_TOKEN_RATES: dict[str, tuple[float, float, float]] = {
    "gpt-4.1": (2.0, 0.5, 8.0),
    "gpt-4.1-mini": (0.4, 0.1, 1.6),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.5": (5.0, 0.5, 30.0),
}

DEFAULT_TOKEN_RATES = MODEL_TOKEN_RATES["gpt-4.1"]


class SpendCapExceeded(Exception):
    """Raised when daily pre-fetch spend reaches the configured cap."""


@dataclass
class UsageRecord:
    section: str
    model: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    web_search_calls: int
    cost_usd: float
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log_line(self) -> str:
        return (
            f"  [{self.section}] usage: in={self.input_tokens} "
            f"(cached={self.cached_tokens}) out={self.output_tokens} "
            f"web_search={self.web_search_calls} → est. ${self.cost_usd:.4f}"
        )


def log(message: str) -> None:
    print(message, flush=True)


def resolve_daily_cap() -> float:
    raw = (os.environ.get("OPENAI_DAILY_SPEND_CAP_USD") or "2").strip()
    try:
        cap = float(raw)
    except ValueError as exc:
        raise ValueError(f"OPENAI_DAILY_SPEND_CAP_USD must be a number, got: {raw!r}") from exc
    return max(0.0, cap)


def normalize_model(model: str) -> str:
    return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model.strip())


def model_token_rates(model: str) -> tuple[float, float, float]:
    key = normalize_model(model)
    if key in MODEL_TOKEN_RATES:
        return MODEL_TOKEN_RATES[key]
    for known, rates in MODEL_TOKEN_RATES.items():
        if key.startswith(known):
            return rates
    log(f"  Warning: unknown model {model!r} for pricing — using gpt-4.1 rates")
    return DEFAULT_TOKEN_RATES


def count_web_search_calls(response: Any) -> int:
    count = 0
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None)
        if item_type == "web_search_call":
            count += 1
        elif isinstance(item, dict) and item.get("type") == "web_search_call":
            count += 1
    return count


def extract_usage_tokens(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0, 0

    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cached_tokens = 0
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
    return input_tokens, cached_tokens, output_tokens


def estimate_response_cost_usd(*, response: Any, model: str) -> tuple[float, int, int, int, int]:
    input_tokens, cached_tokens, output_tokens = extract_usage_tokens(response)
    web_search_calls = count_web_search_calls(response)

    input_rate, cached_rate, output_rate = model_token_rates(model)
    uncached = max(0, input_tokens - cached_tokens)
    token_cost = (
        uncached * input_rate / 1_000_000
        + cached_tokens * cached_rate / 1_000_000
        + output_tokens * output_rate / 1_000_000
    )
    tool_cost = web_search_calls * WEB_SEARCH_COST_PER_CALL_USD
    return token_cost + tool_cost, input_tokens, cached_tokens, output_tokens, web_search_calls


def usage_from_response(*, response: Any, model: str, section: str) -> UsageRecord:
    cost, input_tokens, cached_tokens, output_tokens, web_search_calls = estimate_response_cost_usd(
        response=response,
        model=model,
    )
    return UsageRecord(
        section=section,
        model=model,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        web_search_calls=web_search_calls,
        cost_usd=round(cost, 6),
    )


@dataclass
class DailySpendLedger:
    date: str
    cap_usd: float
    spent_usd: float = 0.0
    estimated: bool = True
    cap_exceeded: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)
    last_run_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _reserved_usd: float = field(default=0.0, repr=False)
    _last_reserve_usd: float = field(default=SECTION_BUDGET_RESERVE_USD, repr=False)

    @classmethod
    def load_or_create(cls, path: Path, *, date_str: str, cap_usd: float) -> DailySpendLedger:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if data.get("date") == date_str:
                return cls(
                    date=date_str,
                    cap_usd=cap_usd,
                    spent_usd=float(data.get("spent_usd") or 0.0),
                    estimated=bool(data.get("estimated", True)),
                    cap_exceeded=bool(data.get("cap_exceeded")),
                    calls=list(data.get("calls") or []),
                    last_run_at=str(data.get("last_run_at") or datetime.now(timezone.utc).isoformat()),
                )
        return cls(date=date_str, cap_usd=cap_usd)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd - self._reserved_usd)

    def is_over_cap(self) -> bool:
        if self.cap_usd <= 0:
            return False
        return self.spent_usd >= self.cap_usd

    def cap_enabled(self) -> bool:
        return self.cap_usd > 0

    def try_reserve_section_budget(
        self,
        *,
        reserve_usd: float | None = None,
    ) -> bool:
        amount = SECTION_BUDGET_RESERVE_USD if reserve_usd is None else reserve_usd
        if not self.cap_enabled():
            return True
        with self._lock:
            if self.spent_usd >= self.cap_usd:
                return False
            if self.spent_usd + self._reserved_usd + amount > self.cap_usd:
                return False
            self._reserved_usd += amount
            self._last_reserve_usd = amount
            return True

    def record_usage(self, usage: UsageRecord) -> None:
        with self._lock:
            self._reserved_usd = max(0.0, self._reserved_usd - self._last_reserve_usd)
            self._last_reserve_usd = SECTION_BUDGET_RESERVE_USD
            self.spent_usd = round(self.spent_usd + usage.cost_usd, 6)
            self.calls.append(asdict(usage))
            self.last_run_at = datetime.now(timezone.utc).isoformat()
            log(usage.log_line())
            log(
                f"  Daily spend: ${self.spent_usd:.4f} / ${self.cap_usd:.2f} cap "
                f"(remaining ${max(0.0, self.cap_usd - self.spent_usd):.4f})"
            )

    def mark_cap_exceeded(self) -> None:
        self.cap_exceeded = True
        self.last_run_at = datetime.now(timezone.utc).isoformat()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": self.date,
            "cap_usd": self.cap_usd,
            "spent_usd": round(self.spent_usd, 6),
            "estimated": self.estimated,
            "cap_exceeded": self.cap_exceeded,
            "calls": self.calls,
            "last_run_at": self.last_run_at,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def assert_not_over_cap(self) -> None:
        if self.cap_enabled() and self.is_over_cap():
            raise SpendCapExceeded(
                f"Daily OpenAI spend cap reached: ${self.spent_usd:.4f} >= ${self.cap_usd:.2f}"
            )


def emit_cap_alert(*, ledger: DailySpendLedger, briefing_label: str, date_str: str) -> None:
    message = (
        f"OpenAI pre-fetch spend cap hit for {briefing_label} on {date_str}: "
        f"${ledger.spent_usd:.4f} of ${ledger.cap_usd:.2f} daily cap."
    )
    log("")
    log("=" * 72)
    log("SPEND_CAP_ALERT: " + message)
    log("=" * 72)
    log("")
    # Surfaces as a failed-check annotation in the GitHub Actions UI.
    print(f"::error title=OpenAI spend cap exceeded::{message}", flush=True)


def write_cap_error_file(path: Path, *, ledger: DailySpendLedger, briefing_label: str) -> None:
    lines = [
        "OpenAI daily spend cap exceeded — pre-fetch aborted.",
        "",
        f"Briefing: {briefing_label}",
        f"Date: {ledger.date}",
        f"Spent (estimated): ${ledger.spent_usd:.4f}",
        f"Cap: ${ledger.cap_usd:.2f}",
        "",
        "No raw inbox was written for this run.",
        "Check inbox/*-spend.json for per-section usage.",
        "",
        "To resume tomorrow (UTC date rolls over) or raise OPENAI_DAILY_SPEND_CAP_USD.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def maybe_send_cap_email(
    *,
    ledger: DailySpendLedger,
    briefing_label: str,
    date_str: str,
) -> None:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    if not api_key or not from_addr or not to_raw:
        log("  (Spend cap email skipped — RESEND_API_KEY / BRIEFING_* not set)")
        return

    to_addrs = [part.strip() for part in to_raw.split(",") if part.strip()]
    subject = f"[Briefing] OpenAI spend cap hit — {briefing_label} {date_str}"
    html = f"""<p><strong>OpenAI pre-fetch spend cap exceeded.</strong></p>
<ul>
  <li>Briefing: {briefing_label}</li>
  <li>Date: {date_str}</li>
  <li>Estimated spend: ${ledger.spent_usd:.4f}</li>
  <li>Daily cap: ${ledger.cap_usd:.2f}</li>
</ul>
<p>Pre-fetch aborted; no raw inbox written. The GitHub pre-fetch workflow should show as failed.</p>
<p>See <code>inbox/*-{date_str}-spend.json</code> in the repo for per-section usage.</p>"""
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_addr,
                "to": to_addrs,
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        if response.ok:
            log("  Spend cap alert email sent via Resend")
        else:
            log(f"  Warning: Resend alert failed ({response.status_code}): {response.text[:200]}")
    except requests.RequestException as exc:
        log(f"  Warning: could not send spend cap email: {exc}")


def handle_cap_abort(
    *,
    ledger: DailySpendLedger,
    spend_path: Path,
    error_path: Path,
    briefing_label: str,
    date_str: str,
) -> None:
    ledger.mark_cap_exceeded()
    ledger.save(spend_path)
    write_cap_error_file(error_path, ledger=ledger, briefing_label=briefing_label)
    emit_cap_alert(ledger=ledger, briefing_label=briefing_label, date_str=date_str)
    maybe_send_cap_email(ledger=ledger, briefing_label=briefing_label, date_str=date_str)
