#!/usr/bin/env python3
"""SessionEnd cache-stats logger. Reads JSON event from stdin, writes JSONL record."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    usage = e.get("usage", {}) or {}
    sess = e.get("session", {}) or {}

    def pick(*keys, default=0):
        for src in (e, sess, usage):
            for k in keys:
                v = src.get(k)
                if v is not None:
                    return v
        return default

    in_tok = pick("input_tokens", default=0) or 0
    out_tok = pick("output_tokens", default=0) or 0
    cache_read = pick("cache_read_input_tokens", "cache_read_tokens", default=0) or 0
    cache_create = (
        pick("cache_creation_input_tokens", "cache_creation_tokens", default=0) or 0
    )
    cost = pick("total_cost_usd", "cost_usd", default=0.0) or 0.0
    duration = pick("duration_ms", default=0) or 0

    sid = e.get("session_id") or sess.get("id") or e.get("uuid") or "unknown"
    model = e.get("model") or sess.get("model") or "unknown"
    if isinstance(model, dict):
        model = model.get("id") or "unknown"
    reason = e.get("reason") or e.get("matcher") or e.get("terminal_reason") or "unknown"

    total = in_tok + cache_read + cache_create
    hit_rate = (cache_read / total) if total else 0.0

    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": sid,
        "model": model,
        "reason": reason,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_create,
        "cache_hit_rate": round(hit_rate, 4),
        "cost_usd": round(cost, 4),
        "duration_ms": duration,
    }

    stats_dir = os.path.expanduser("~/.claude/telemetry")
    os.makedirs(stats_dir, exist_ok=True)
    with open(os.path.join(stats_dir, "cache-stats.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")

    if total > 50_000 and hit_rate < 0.70:
        with open(os.path.join(stats_dir, "cache-anomalies.jsonl"), "a") as f:
            f.write(json.dumps({**rec, "anomaly": "low_cache_hit_rate"}) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
