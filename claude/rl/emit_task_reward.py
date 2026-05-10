#!/usr/bin/env python3
"""
TaskCompleted hook: emit a reward event based on verifier + critic evidence
in the active session's transcript.

Reads JSON event from stdin (session_id, task info), greps the session's JSONL
for recent RESULT_verifier= and RESULT_critic= lines, computes reward, appends
to rewards.jsonl.

Always exits 0 — this hook is for telemetry, not gating.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RL_DIR = Path.home() / ".claude" / "rl"
PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_session_jsonl(session_id: str) -> Path | None:
    if not session_id:
        return None
    matches = list(PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


def parse_recent_results(jsonl_path: Path, lookback_lines: int = 400) -> dict:
    """Tail the JSONL and pull out the most recent RESULT_<agent>= signals."""
    if not jsonl_path or not jsonl_path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        with jsonl_path.open() as f:
            lines = f.readlines()[-lookback_lines:]
    except OSError:
        return out
    for line in reversed(lines):
        for match in re.finditer(r"RESULT_([\w-]+)=([A-Z_]+(?:_\d+)*)", line):
            agent, status = match.group(1), match.group(2)
            out.setdefault(agent, status)
    return out


def emit_reward(rec: dict) -> None:
    RL_DIR.mkdir(parents=True, exist_ok=True)
    with (RL_DIR / "rewards.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    sid = e.get("session_id") or ""
    task = e.get("task") or {}
    if isinstance(task, str):
        task_text = task
    else:
        task_text = task.get("content") or task.get("description") or ""

    jsonl = find_session_jsonl(sid)
    results = parse_recent_results(jsonl) if jsonl else {}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Verifier reward
    verifier_status = results.get("verifier", "")
    if verifier_status == "PASS":
        emit_reward({
            "ts": ts, "session_id": sid, "agent": "verifier",
            "source": "task_completed", "signal": "verifier_pass",
            "reward": 1.0, "evidence": f"RESULT_verifier={verifier_status}",
            "task_excerpt": task_text[:200],
        })
    elif verifier_status == "FAIL":
        emit_reward({
            "ts": ts, "session_id": sid, "agent": "verifier",
            "source": "task_completed", "signal": "verifier_fail",
            "reward": -1.0, "evidence": f"RESULT_verifier={verifier_status}",
            "task_excerpt": task_text[:200],
        })

    # Critic reward
    critic_status = results.get("critic", "")
    if critic_status == "CLEAN":
        emit_reward({
            "ts": ts, "session_id": sid, "agent": "critic",
            "source": "task_completed", "signal": "critic_clean",
            "reward": 0.5, "evidence": f"RESULT_critic={critic_status}",
        })
    elif critic_status.startswith("HAS_FINDINGS"):
        # Parse counts: HAS_FINDINGS_<critical>_<high>
        parts = critic_status.split("_")
        try:
            n_crit = int(parts[2]) if len(parts) > 2 else 0
            n_high = int(parts[3]) if len(parts) > 3 else 0
        except (ValueError, IndexError):
            n_crit = n_high = 0
        weighted = n_crit * 1.0 + n_high * 0.5
        reward = max(-2.0, -0.5 * weighted)
        emit_reward({
            "ts": ts, "session_id": sid, "agent": "critic",
            "source": "task_completed", "signal": "critic_findings",
            "reward": reward,
            "evidence": critic_status,
            "n_critical": n_crit, "n_high": n_high,
        })

    # Baseline: task closed at all → small positive
    if not verifier_status and not critic_status:
        emit_reward({
            "ts": ts, "session_id": sid, "agent": "session",
            "source": "task_completed", "signal": "task_closed_no_evidence",
            "reward": 0.1, "evidence": "no RESULT_* found",
            "task_excerpt": task_text[:200],
        })

    return 0


if __name__ == "__main__":
    sys.exit(main())
