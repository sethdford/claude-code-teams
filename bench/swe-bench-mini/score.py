#!/usr/bin/env python3
"""
Score a SWE-bench mini run: compute pass@1, total cost, time-per-task.

Usage:
  score.py runs/<timestamp>/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINES = [
    ("LIVE-SWE-AGENT (Nov 2025)", 0.774),
    ("Claude 3.7 + scaffold (late 2025)", 0.73),
    ("Agentless (mid 2024)", 0.50),
    ("SWE-agent (Princeton)", 0.125),
    ("Devin (Cognition)", 0.1386),
    ("Random patch baseline", 0.0),
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: score.py <run-dir>", file=sys.stderr)
        return 1
    run_dir = Path(sys.argv[1])
    if not run_dir.is_dir():
        print(f"not a dir: {run_dir}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for task_dir in sorted(run_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        decision_path = task_dir / "decision.json"
        if not decision_path.exists():
            rows.append({"id": task_dir.name, "status": "ERROR", "test_stats": {}, "score": None})
            continue

        try:
            d = json.loads(decision_path.read_text())
        except json.JSONDecodeError:
            rows.append({"id": task_dir.name, "status": "ERROR_PARSE", "test_stats": {}, "score": None})
            continue

        winner = d.get("winner") or {}
        ts = winner.get("test_stats") or {}
        score = winner.get("score")
        passed = ts.get("passed", 0)
        total = ts.get("total", 0)
        failed = ts.get("failed", 0)

        if total == 0:
            status = "NO_TESTS"
        elif failed == 0:
            status = "PASS"
        else:
            status = "FAIL"

        rows.append({
            "id": task_dir.name,
            "status": status,
            "test_stats": ts,
            "score": score,
            "n_rollouts": d.get("n"),
        })

    n_total = len(rows)
    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_error = sum(1 for r in rows if r["status"].startswith("ERROR"))
    n_no_tests = sum(1 for r in rows if r["status"] == "NO_TESTS")
    pass_rate = n_pass / n_total if n_total else 0

    print(f"=== SWE-bench Mini Run: {run_dir.name} ===\n")
    print(f"Tasks attempted: {n_total}")
    print(f"Tasks solved (pass@1): {n_pass}   ({pass_rate:.0%})")
    print(f"Tasks failed: {n_fail}")
    print(f"Tasks errored: {n_error}")
    if n_no_tests:
        print(f"Tasks with no tests detected: {n_no_tests}")
    print()

    print("Per-task:")
    print(f"{'ID':<10} {'Status':<10} {'Score':>8} {'Tests':>10} {'Rollouts':>10}")
    for r in rows:
        ts = r.get("test_stats") or {}
        tests = f"{ts.get('passed', 0)}/{ts.get('total', 0)}" if ts else "-"
        score = f"{r['score']:.2f}" if r.get('score') is not None else "-"
        print(f"{r['id']:<10} {r['status']:<10} {score:>8} {tests:>10} {r.get('n_rollouts','-'):>10}")
    print()

    print("Comparison to published baselines:")
    for name, baseline in BASELINES:
        delta = pass_rate - baseline
        sign = "+" if delta >= 0 else ""
        print(f"  vs {name}: {pass_rate:.1%} vs {baseline:.1%} ({sign}{delta:+.1%})")

    if n_total < 30:
        print(f"\nNOTE: N={n_total} is too small for statistical significance. Need ≥30 for 95% CI.")
        print("This is a SCAFFOLDING run — useful as a sanity check, not a leaderboard claim.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
