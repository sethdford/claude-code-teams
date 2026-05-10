#!/usr/bin/env python3
"""
A/B test framework for agent prompt variants.

Compares an agent's current prompt against candidate prompts in
~/.claude/rl/policy/<agent>/candidates/ by running each on the same
held-out scenarios and aggregating reward.

Promotion rule: candidate's mean_reward > current's by >1 stderr AND n >= 10
(per scenarios * variants run count).

Usage:
  ab_test.py <agent> [--candidate <path>] [--scenarios <dir>] [--runs 3]
  ab_test.py <agent> --promote <candidate-name>   # apply approved candidate

Output:
  ~/.claude/rl/policy/<agent>/ab-runs/<ts>/
    ├── current/ <run-N>.jsonl
    ├── candidate-<name>/ <run-N>.jsonl
    └── decision.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, pstdev

RL_DIR = Path.home() / ".claude" / "rl"
AGENTS_DIR = Path.home() / ".claude" / "agents"


def get_paths(agent: str) -> dict[str, Path]:
    return {
        "live": AGENTS_DIR / f"{agent}.md",
        "policy": RL_DIR / "policy" / agent,
        "candidates": RL_DIR / "policy" / agent / "candidates",
        "history": RL_DIR / "policy" / agent / "history",
        "ab_runs": RL_DIR / "policy" / agent / "ab-runs",
    }


def claude_flags(max_budget: float = 0.5) -> list[str]:
    base = [
        "-p", "--output-format", "stream-json", "--max-turns", "5",
        "--max-budget-usd", str(max_budget),
        "--allowedTools", "Read,Glob,Grep,Bash,Edit,Write,Agent,Skill,Task",
        "--no-session-persistence", "--verbose",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + ["--setting-sources", "user", "--exclude-dynamic-system-prompt-sections"]


def run_scenario(
    agent: str, scenario_path: Path, agent_md_path: Path, out_dir: Path, idx: int
) -> dict:
    """Run a scenario against a specific agent prompt; return parsed results."""
    text = scenario_path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {"error": "no frontmatter"}
    fm = m.group(1)
    prompt_match = re.search(r"^prompt:\s*(.+)$", fm, flags=re.M)
    if not prompt_match:
        return {"error": "no prompt in frontmatter"}
    prompt = prompt_match.group(1).strip().strip("'\"")

    # We use --append-system-prompt-file to inject the candidate prompt
    # The agent .md file's body is the system prompt
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / f"run-{idx}.jsonl"
    stderr = out_dir / f"run-{idx}.stderr"

    cmd = ["claude"] + claude_flags(max_budget=0.3) + [
        "--append-system-prompt-file", str(agent_md_path),
    ]

    try:
        with jsonl.open("w") as out_f, stderr.open("w") as err_f:
            proc = subprocess.run(
                cmd, input=prompt, text=True, stdout=out_f, stderr=err_f,
                timeout=180, check=False,
            )
    except subprocess.TimeoutExpired:
        return {"jsonl": str(jsonl), "error": "timeout"}

    # Parse RESULT_<agent>=
    results: dict[str, str] = {}
    try:
        for line in jsonl.read_text().splitlines():
            for m in re.finditer(r"RESULT_([\w-]+)=([A-Z_]+(?:_\d+)*)", line):
                results.setdefault(m.group(1), m.group(2))
    except OSError:
        pass

    # Score: 1.0 PASS / CLEAN, -1.0 FAIL, 0 otherwise
    target_status = results.get(agent, "")
    score = {"PASS": 1.0, "CLEAN": 0.7, "FAIL": -1.0, "INCONCLUSIVE": 0.0}.get(
        target_status, 0.0
    )

    return {
        "scenario": scenario_path.stem,
        "exit": proc.returncode if "proc" in locals() else -1,
        "results": results, "score": score, "jsonl": str(jsonl),
    }


def aggregate(runs: list[dict]) -> dict:
    scores = [r.get("score", 0.0) for r in runs if "error" not in r]
    if not scores:
        return {"n": 0, "mean": 0.0, "stderr": 0.0, "errors": len(runs)}
    return {
        "n": len(scores),
        "mean": round(fmean(scores), 4),
        "stderr": round(pstdev(scores) / max(1, len(scores) ** 0.5), 4) if len(scores) > 1 else 0.0,
        "errors": len(runs) - len(scores),
        "raw": scores,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--candidate", help="path to a candidate .md (defaults to all in candidates/)")
    ap.add_argument("--scenarios", help="dir of .md scenarios (defaults to evals/scenarios/<agent>/)")
    ap.add_argument("--runs", type=int, default=3, help="repetitions per scenario for variance estimate")
    ap.add_argument("--promote", help="instead of A/B, promote a named candidate to live")
    args = ap.parse_args()

    paths = get_paths(args.agent)

    if args.promote:
        cand_path = paths["candidates"] / f"{args.promote}.md"
        if not cand_path.exists():
            cand_path = paths["candidates"] / args.promote  # may include .md already
        if not cand_path.exists():
            print(f"[ab-test] no candidate found at {cand_path}", file=sys.stderr)
            return 1
        # Backup current → history
        paths["history"].mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(paths["live"], paths["history"] / f"{ts}.md")
        shutil.copy2(cand_path, paths["live"])
        print(f"[ab-test] PROMOTED {cand_path} -> {paths['live']}")
        print(f"[ab-test] previous live archived at {paths['history']}/{ts}.md")
        return 0

    if not paths["live"].exists():
        print(f"[ab-test] no agent at {paths['live']}", file=sys.stderr)
        return 1

    candidates_dir = paths["candidates"]
    if args.candidate:
        candidates = [Path(args.candidate)]
    elif candidates_dir.exists():
        candidates = sorted(candidates_dir.glob("*.md"))
    else:
        candidates = []

    if not candidates:
        print("[ab-test] no candidates to test", file=sys.stderr)
        return 1

    scenarios_dir = (
        Path(args.scenarios)
        if args.scenarios
        else Path.home() / ".claude" / "evals" / "scenarios" / args.agent
    )
    scenarios = sorted(p for p in scenarios_dir.glob("*.md") if p.name != "README.md")
    if not scenarios:
        print(f"[ab-test] no scenarios at {scenarios_dir}", file=sys.stderr)
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = paths["ab_runs"] / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ab-test] {args.agent}: {len(scenarios)} scenarios x {args.runs} runs x {1 + len(candidates)} variants")

    # Run current
    current_runs: list[dict] = []
    for scenario in scenarios:
        for k in range(args.runs):
            r = run_scenario(args.agent, scenario, paths["live"],
                             run_dir / "current" / scenario.stem, k)
            current_runs.append(r)

    # Run candidates
    candidate_results: dict[str, list[dict]] = {}
    for cand in candidates:
        cand_name = cand.stem
        cand_runs: list[dict] = []
        for scenario in scenarios:
            for k in range(args.runs):
                r = run_scenario(args.agent, scenario, cand,
                                 run_dir / f"candidate-{cand_name}" / scenario.stem, k)
                cand_runs.append(r)
        candidate_results[cand_name] = cand_runs

    # Decision
    current_agg = aggregate(current_runs)
    decision = {
        "ts": ts,
        "agent": args.agent,
        "scenarios": [s.stem for s in scenarios],
        "runs_per_scenario": args.runs,
        "current": current_agg,
        "candidates": {},
        "winner": None,
        "promote": False,
    }

    best_cand_name = None
    best_cand_agg = None
    for name, runs in candidate_results.items():
        cand_agg = aggregate(runs)
        decision["candidates"][name] = cand_agg
        if cand_agg["n"] >= 10 and cand_agg["mean"] > current_agg["mean"] + max(
            current_agg["stderr"], 0.05
        ):
            if best_cand_agg is None or cand_agg["mean"] > best_cand_agg["mean"]:
                best_cand_name = name
                best_cand_agg = cand_agg

    if best_cand_name:
        decision["winner"] = best_cand_name
        decision["promote"] = True
        decision["promote_command"] = f"python3 ~/.claude/rl/ab_test.py {args.agent} --promote {best_cand_name}"

    (run_dir / "decision.json").write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
