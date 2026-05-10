#!/usr/bin/env python3
"""
Custom statusline for Claude Code.

Receives JSON on stdin from the harness:
  {
    "model": {"id": "...", "display_name": "..."},
    "session": {"id": "...", "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0,
                "context_pct": 0.0, "lines_added": 0, "lines_removed": 0},
    "workspace": {"current_dir": "...", "worktree_branch": null},
    "rate_limits": {"5h_used_pct": 0, "7d_used_pct": 0}
  }

(The exact field set varies by version; we read defensively.)

Prints a single-line statusline with cache hit rate, model, cost, and context use.
Designed to be cheap (~10ms) and resilient to schema drift.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def _hit_rate_color(rate: float) -> str:
    if rate >= 0.85:
        return "32"  # green
    if rate >= 0.70:
        return "33"  # yellow
    return "31"  # red


def _ctx_color(pct: float) -> str:
    if pct < 50:
        return "32"
    if pct < 80:
        return "33"
    return "31"


def _short_model(mid: str) -> str:
    if "opus" in mid:
        return "opus"
    if "sonnet" in mid:
        return "sonnet"
    if "haiku" in mid:
        return "haiku"
    return mid.split("-")[-1] if "-" in mid else mid


def main() -> None:
    data = _read_input()

    sess = data.get("session", {}) or {}
    model = data.get("model", {}) or {}
    ws = data.get("workspace", {}) or {}

    # Schema: Anthropic-canonical names use *_input_tokens for cache fields.
    # Tolerate either naming since claude-code may surface a flat or nested shape.
    usage = sess.get("usage", {}) or {}
    in_tok = sess.get("input_tokens", usage.get("input_tokens", 0)) or 0
    out_tok = sess.get("output_tokens", usage.get("output_tokens", 0)) or 0
    cache_read = (
        sess.get("cache_read_input_tokens")
        or sess.get("cache_read_tokens")
        or usage.get("cache_read_input_tokens", 0)
        or 0
    )
    cache_write = (
        sess.get("cache_creation_input_tokens")
        or sess.get("cache_creation_tokens")
        or usage.get("cache_creation_input_tokens", 0)
        or 0
    )
    cost = sess.get("total_cost_usd", sess.get("cost_usd", 0.0)) or 0.0
    ctx_pct = sess.get("context_pct", 0.0) or 0.0

    total_input_billable = in_tok + cache_read + cache_write
    if total_input_billable > 0:
        cache_hit_rate = cache_read / total_input_billable
    else:
        cache_hit_rate = 0.0

    model_name = _short_model(model.get("id") or model.get("display_name") or "?")
    branch = ws.get("worktree_branch")
    cwd = ws.get("current_dir", "") or ""
    cwd_short = "/".join(cwd.rstrip("/").split("/")[-2:]) if cwd else "?"

    parts: list[str] = []
    parts.append(_color(model_name, "1;36"))  # bold cyan
    parts.append(
        _color(f"cache {cache_hit_rate:.0%}", _hit_rate_color(cache_hit_rate))
    )
    parts.append(_color(f"ctx {ctx_pct:.0f}%", _ctx_color(ctx_pct)))
    parts.append(f"${cost:.2f}")
    parts.append(f"in {in_tok//1000}k+{cache_read//1000}kc / out {out_tok//1000}k")
    if branch:
        parts.append(_color(f"{branch}", "35"))  # magenta
    parts.append(_color(cwd_short, "90"))  # gray

    line = " │ ".join(parts)

    log_dir = Path.home() / ".claude" / "telemetry"
    log_dir.mkdir(parents=True, exist_ok=True)
    snap = log_dir / "statusline-last.json"
    try:
        snap.write_text(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "model": model_name,
                    "cache_hit_rate": round(cache_hit_rate, 4),
                    "context_pct": ctx_pct,
                    "cost_usd": cost,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_write,
                }
            )
        )
    except OSError:
        pass

    sys.stdout.write(line)


if __name__ == "__main__":
    main()
