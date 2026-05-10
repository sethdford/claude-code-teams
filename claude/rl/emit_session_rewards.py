#!/usr/bin/env python3
"""
SessionEnd hook: aggregate the session's reward events and update value/<agent>.json.

Reads SessionEnd event from stdin (session_id, total_cost_usd, etc.). Walks
rewards.jsonl filtering by session_id, aggregates per agent, updates value/.

Also emits one session-level reward event summarizing cache hit rate and cost
sanity (anomalies → small negative reward).

Always exits 0.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

RL_DIR = Path.home() / ".claude" / "rl"
VALUE_DIR = RL_DIR / "value"


def emit(rec: dict) -> None:
    RL_DIR.mkdir(parents=True, exist_ok=True)
    with (RL_DIR / "rewards.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def update_value_for_agent(agent: str) -> None:
    """Recompute value/<agent>.json from rewards.jsonl."""
    rewards_path = RL_DIR / "rewards.jsonl"
    if not rewards_path.exists():
        return

    rewards: list[dict] = []
    with rewards_path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("agent") == agent:
                rewards.append(r)

    if not rewards:
        return

    now = datetime.now(timezone.utc)
    in_window = lambda r, days: (
        now - datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
    ) < timedelta(days=days)

    last7 = [r for r in rewards if in_window(r, 7)]
    last30 = [r for r in rewards if in_window(r, 30)]

    def agg(rs: list[dict]) -> dict:
        if not rs:
            return {"n": 0, "mean": 0.0, "stderr": 0.0}
        vals = [r.get("reward", 0.0) for r in rs]
        n = len(vals)
        mean = statistics.fmean(vals)
        stderr = (statistics.pstdev(vals) / max(1, n**0.5)) if n > 1 else 0.0
        return {"n": n, "mean": round(mean, 4), "stderr": round(stderr, 4)}

    out = {
        "agent": agent,
        "n_runs": len(rewards),
        "mean_reward": round(statistics.fmean([r.get("reward", 0.0) for r in rewards]), 4),
        "rolling_7d": agg(last7),
        "rolling_30d": agg(last30),
        "last_updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    VALUE_DIR.mkdir(parents=True, exist_ok=True)
    (VALUE_DIR / f"{agent}.json").write_text(json.dumps(out, indent=2))


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    sid = e.get("session_id") or e.get("uuid") or ""
    cost = e.get("total_cost_usd", 0.0) or 0.0
    usage = e.get("usage", {}) or {}
    in_tok = usage.get("input_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_create = usage.get("cache_creation_input_tokens", 0) or 0
    total = in_tok + cache_read + cache_create
    hit_rate = (cache_read / total) if total else 0.0

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Session-level rewards: anomaly penalties
    if total > 50_000 and hit_rate < 0.70:
        emit({
            "ts": ts, "session_id": sid, "agent": "session",
            "source": "session_end", "signal": "low_cache_hit_rate",
            "reward": -0.3, "cache_hit_rate": round(hit_rate, 4),
            "cost_usd": round(cost, 4),
        })

    # Recompute value for every agent that received rewards in this session
    rewards_path = RL_DIR / "rewards.jsonl"
    agents_touched: set[str] = set()
    if rewards_path.exists():
        with rewards_path.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("session_id") == sid and r.get("agent"):
                    agents_touched.add(r["agent"])

    for agent in agents_touched:
        update_value_for_agent(agent)

    return 0


if __name__ == "__main__":
    sys.exit(main())
