#!/usr/bin/env python3
"""
Execution-grounded Best-of-N for code-change candidates.

Pattern: SWE-bench leaders spend 60-80% of compute on verification, not generation.
This module flips our default. For a code-change task, run N rollouts in
isolated sandbox dirs, run a test command in each, score by tests-passed first,
critic-score second.

Usage:
  exec_grounded.py <agent> <prompt> --target-dir ./src --test-cmd "pytest -q" --n 3

Per rollout:
  1. Stage:  cp -r <target-dir> /tmp/bon-<ts>-<idx>/
  2. Run:    claude -p with --add-dir /tmp/bon-<ts>-<idx>/, agent does work in CWD
  3. Verify: sandbox_run.py --cwd /tmp/bon-<ts>-<idx>/ -- <test-cmd>
  4. Parse:  exit=0 + extract pytest-style "N passed, M failed" from stdout
  5. Score:  test_score * 0.7 + critic_score * 0.3, where
             test_score = 1.0 (all green), 0.0 (any red), 0.5 (no tests found)

Output:
  decision.json with per-rollout test scores + winner
  Reward emitted to ~/.claude/rl/rewards.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RL_DIR = Path.home() / ".claude" / "rl"
SANDBOX_RUN = Path.home() / ".claude" / "sandbox" / "sandbox_run.py"


def claude_flags(workdir: str, max_budget: float = 1.0) -> list[str]:
    base = [
        "-p",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--max-turns", "12",
        "--max-budget-usd", str(max_budget),
        "--add-dir", workdir,
        "--allowedTools", "Read,Glob,Grep,Bash,Edit,Write,MultiEdit,Agent",
        "--no-session-persistence",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + ["--setting-sources", "user", "--exclude-dynamic-system-prompt-sections"]


def stage_workdir(target_dir: Path, idx: int, run_dir: Path) -> Path:
    """Copy target_dir to a per-rollout sandbox dir."""
    workdir = run_dir / f"work-{idx}"
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(target_dir, workdir, symlinks=True, ignore=shutil.ignore_patterns(
        "node_modules", ".git", "__pycache__", "*.pyc", ".venv", "venv", "dist", "build", ".next"
    ))
    return workdir


def parse_test_output(stdout: str, stderr: str) -> dict:
    """
    Extract test stats from common runners:
      pytest:  "N passed, M failed, K errors in T s"
      jest:    "Tests: A failed, B passed, C total"
      vitest:  similar
      go test: "FAIL" / "ok" + "PASS"

    Returns: {passed: int, failed: int, total: int, runner: str}
    """
    text = stdout + "\n" + stderr

    # jest/vitest pattern (must check BEFORE pytest because "Tests: ... passed" is more specific)
    m = re.search(r"Tests:\s*(?:(\d+) failed,\s*)?(\d+) passed,\s*(\d+) total", text)
    if m:
        failed = int(m.group(1) or 0)
        passed = int(m.group(2))
        total = int(m.group(3))
        return {"passed": passed, "failed": failed, "total": total, "runner": "jest"}

    # pytest pattern: "N passed, M failed, K errors in T s"
    m = re.search(r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) error)?", text)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2)) if m.group(2) else 0
        errors = int(m.group(3)) if m.group(3) else 0
        return {"passed": passed, "failed": failed + errors, "total": passed + failed + errors, "runner": "pytest"}

    # go test: count PASS/FAIL lines
    if "PASS" in text or "FAIL" in text:
        passed = len(re.findall(r"^\s*--- PASS:", text, re.M))
        failed = len(re.findall(r"^\s*--- FAIL:", text, re.M))
        if passed + failed > 0:
            return {"passed": passed, "failed": failed, "total": passed + failed, "runner": "go-test"}

    return {"passed": 0, "failed": 0, "total": 0, "runner": "unknown"}


def verify_in_sandbox(workdir: Path, test_cmd: list[str], allow_network: bool = False) -> dict:
    """Run test command in sandbox, parse results."""
    if not SANDBOX_RUN.exists():
        return {"sandboxed": False, "error": "sandbox_run.py not found", "exit_code": -1}

    cmd = ["python3", str(SANDBOX_RUN), "--cwd", str(workdir), "--json"]
    if allow_network:
        cmd.append("--allow-network")
    cmd.append("--")
    cmd.extend(test_cmd)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"sandboxed": True, "exit_code": -1, "timed_out": True,
                "stdout": "", "stderr": "TIMEOUT", "test_stats": {}}

    try:
        result = json.loads(proc.stdout.strip().split("\n")[-1])
    except (json.JSONDecodeError, IndexError):
        return {"sandboxed": False, "exit_code": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr, "test_stats": {}}

    result["test_stats"] = parse_test_output(result.get("stdout", ""), result.get("stderr", ""))
    return result


def run_rollout(idx: int, agent: str, prompt: str, workdir: Path, run_dir: Path,
                test_cmd: list[str], max_budget: float, allow_network: bool) -> dict:
    """Run one rollout: agent works in workdir, then test_cmd runs in sandbox."""
    jsonl = run_dir / f"rollout-{idx}.jsonl"
    stderr = run_dir / f"rollout-{idx}.stderr"

    framed = (
        f"You are working in {workdir}. Use the {agent} agent to complete this task. "
        f"Run any tests yourself if helpful, but the final test verification will be "
        f"run separately in a sandbox.\n\n{prompt}"
    )

    flags = claude_flags(str(workdir), max_budget=max_budget)
    start = time.time()
    try:
        with jsonl.open("w") as out_f, stderr.open("w") as err_f:
            proc = subprocess.run(
                ["claude"] + flags, input=framed, text=True,
                stdout=out_f, stderr=err_f, timeout=900, check=False,
            )
        rollout_exit = proc.returncode
    except subprocess.TimeoutExpired:
        rollout_exit = -1

    rollout_elapsed = time.time() - start

    # Verify in sandbox
    verify_start = time.time()
    verify_result = verify_in_sandbox(workdir, test_cmd, allow_network=allow_network)
    verify_elapsed = time.time() - verify_start

    # Parse RESULT_<agent>= from rollout
    results: dict[str, str] = {}
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            for m in re.finditer(r"RESULT_([\w-]+)=([A-Z_]+(?:_\d+)*)", line):
                results.setdefault(m.group(1), m.group(2))

    return {
        "idx": idx,
        "workdir": str(workdir),
        "rollout_exit": rollout_exit,
        "rollout_elapsed_s": round(rollout_elapsed, 2),
        "verify_exit": verify_result.get("exit_code", -1),
        "verify_elapsed_s": round(verify_elapsed, 2),
        "test_stats": verify_result.get("test_stats", {}),
        "results": results,
        "verify_stdout_excerpt": verify_result.get("stdout", "")[-500:],
        "verify_stderr_excerpt": verify_result.get("stderr", "")[-500:],
    }


def score_rollout(rollout: dict) -> float:
    """Combined score in [-1, 1]. test_score dominates (0.7 weight)."""
    stats = rollout.get("test_stats", {}) or {}
    total = stats.get("total", 0)
    passed = stats.get("passed", 0)
    failed = stats.get("failed", 0)

    if total == 0:
        # No tests detected — neutral
        test_score = 0.0
    elif failed == 0 and rollout.get("verify_exit") == 0:
        test_score = 1.0
    elif passed > 0:
        # Partial credit: ratio of passing
        test_score = (passed - failed) / total  # range [-1, 1]
    else:
        test_score = -1.0

    # Critic from RESULT_critic=
    critic = 0.0
    cs = rollout.get("results", {}).get("critic", "")
    if cs == "CLEAN":
        critic = 0.7
    elif cs.startswith("HAS_FINDINGS"):
        critic = -0.5

    score = test_score * 0.7 + critic * 0.3
    rollout["test_score"] = round(test_score, 4)
    rollout["critic_score"] = round(critic, 4)
    rollout["score"] = round(score, 4)
    return score


def emit_reward(decision: dict) -> None:
    RL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    winner = decision.get("winner") or {}
    rec = {
        "ts": ts,
        "agent": decision.get("agent", "unknown"),
        "source": "exec_grounded_bon",
        "signal": "exec_grounded_decision",
        "reward": winner.get("score", 0.0),
        "n": decision.get("n"),
        "test_pass_rate": (winner.get("test_stats", {}).get("passed", 0) /
                           max(1, winner.get("test_stats", {}).get("total", 1))),
        "out_dir": decision.get("out_dir"),
    }
    with (RL_DIR / "rewards.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Execution-grounded Best-of-N")
    ap.add_argument("agent", help="Agent name (e.g., general-purpose, verifier)")
    ap.add_argument("prompt", help="The task prompt")
    ap.add_argument("--target-dir", required=True, type=Path,
                    help="Codebase to fork per rollout")
    ap.add_argument("--test-cmd", required=True,
                    help="Test command to run in sandbox after each rollout (e.g. 'pytest -q')")
    ap.add_argument("--n", type=int, default=3, help="Number of rollouts (2-8)")
    ap.add_argument("--out", type=Path, default=None, help="Output dir")
    ap.add_argument("--max-budget-usd", type=float, default=1.0)
    ap.add_argument("--allow-network", action="store_true",
                    help="Permit network in sandbox (for tests that need it)")
    args = ap.parse_args()

    if args.n < 2 or args.n > 8:
        print("[exec-grounded] --n must be in [2, 8]", file=sys.stderr)
        return 1

    target = args.target_dir.resolve()
    if not target.is_dir():
        print(f"[exec-grounded] target-dir does not exist: {target}", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out if args.out else (RL_DIR / "exec-grounded-runs" / timestamp)
    run_dir.mkdir(parents=True, exist_ok=True)

    test_cmd_list = args.test_cmd.split()

    print(f"[exec-grounded] agent={args.agent} n={args.n} target={target}", file=sys.stderr)
    print(f"[exec-grounded] test_cmd={test_cmd_list}", file=sys.stderr)
    print(f"[exec-grounded] run_dir={run_dir}", file=sys.stderr)

    # Stage all sandbox copies upfront
    workdirs = [stage_workdir(target, i, run_dir) for i in range(args.n)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.n) as ex:
        futures = [
            ex.submit(run_rollout, i, args.agent, args.prompt, workdirs[i], run_dir,
                      test_cmd_list, args.max_budget_usd, args.allow_network)
            for i in range(args.n)
        ]
        rollouts = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in rollouts:
        score_rollout(r)
    rollouts.sort(key=lambda r: r["score"], reverse=True)
    winner = rollouts[0]

    decision = {
        "ts": timestamp,
        "agent": args.agent,
        "n": args.n,
        "target_dir": str(target),
        "test_cmd": test_cmd_list,
        "rollouts": rollouts,
        "winner": {
            "idx": winner["idx"],
            "score": winner["score"],
            "test_score": winner.get("test_score"),
            "critic_score": winner.get("critic_score"),
            "test_stats": winner.get("test_stats"),
            "workdir": winner["workdir"],
        },
        "out_dir": str(run_dir),
    }
    (run_dir / "decision.json").write_text(json.dumps(decision, indent=2))
    emit_reward(decision)

    # Print summary
    print(json.dumps({
        "n": args.n,
        "winner_idx": winner["idx"],
        "winner_score": winner["score"],
        "winner_test_stats": winner.get("test_stats"),
        "spread": round(rollouts[0]["score"] - rollouts[-1]["score"], 4),
        "out_dir": str(run_dir),
    }, indent=2))

    return 0 if winner["score"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
