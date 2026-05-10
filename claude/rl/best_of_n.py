#!/usr/bin/env python3
"""
Best-of-N runner: invoke an agent N times in parallel, score each output with
the critic, pick the highest-scored. Test-time scaling for high-stakes calls.

Usage:
  best_of_n.py <agent-name> <prompt> [--n 3] [--out <dir>]

Output:
  <out>/run-<i>.jsonl       per-rollout transcripts
  <out>/scores.json         per-rollout scores
  <out>/winner.jsonl        the chosen rollout (symlinked)
  <out>/decision.json       summary: {chosen_idx, scores, reward_emit}

Scoring: parses RESULT_<agent>= from output. Then runs critic on the agent's
final assistant message. Combined score = verifier_score * 0.7 + critic_score * 0.3.

Authentication mirrors the eval runner: uses --bare if ANTHROPIC_API_KEY is set,
otherwise --setting-sources user with subscription auth.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RL_DIR = Path.home() / ".claude" / "rl"


def claude_flags(max_budget: float = 1.0) -> list[str]:
    base = [
        "-p",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--include-hook-events",
        "--verbose",
        "--max-turns", "8",
        "--max-budget-usd", str(max_budget),
        "--allowedTools", "Read,Glob,Grep,Bash,Edit,Write,Agent,Skill,Task",
        "--no-session-persistence",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + ["--setting-sources", "user", "--exclude-dynamic-system-prompt-sections"]


def run_one(idx: int, agent: str, prompt: str, out_dir: Path, max_budget: float) -> dict:
    """Run a single rollout. Returns {idx, jsonl, status, result_lines, error}."""
    jsonl = out_dir / f"run-{idx}.jsonl"
    stderr = out_dir / f"run-{idx}.stderr"

    # Prefix the prompt to force the agent to be invoked
    framed = f"Use the {agent} agent for this. {prompt}"

    cmd = ["claude"] + claude_flags(max_budget=max_budget)
    start = time.time()
    try:
        with jsonl.open("w") as out_f, stderr.open("w") as err_f:
            proc = subprocess.run(
                cmd, input=framed, text=True, stdout=out_f, stderr=err_f,
                timeout=300, check=False,
            )
        elapsed = time.time() - start
        # Parse RESULT_ lines from output
        results: dict[str, str] = {}
        try:
            for line in jsonl.read_text().splitlines():
                for m in re.finditer(r"RESULT_([\w-]+)=([A-Z_]+(?:_\d+)*)", line):
                    results.setdefault(m.group(1), m.group(2))
        except OSError:
            pass
        return {
            "idx": idx, "jsonl": str(jsonl), "exit": proc.returncode,
            "elapsed_s": round(elapsed, 2), "results": results,
        }
    except subprocess.TimeoutExpired:
        return {"idx": idx, "jsonl": str(jsonl), "exit": -1, "error": "timeout"}


def extract_confidence(rollout: dict) -> float:
    """Parse self-reported confidence from rollout output. Default 0.5 if absent.

    Looks for `CONFIDENCE: 0.7` style lines; tolerant of variants.
    """
    jsonl = rollout.get("jsonl")
    if not jsonl:
        return 0.5
    try:
        text = open(jsonl).read()
    except OSError:
        return 0.5
    m = re.search(r"\bCONFIDENCE:\s*([\d.]+)", text)
    if not m:
        return 0.5
    try:
        c = float(m.group(1))
        return max(0.0, min(1.0, c))
    except ValueError:
        return 0.5


def score_rollout(rollout: dict, target_agent: str, weight_by_confidence: bool = False) -> float:
    """Combined score in [-1, 1]. Verifier dominates.

    With weight_by_confidence=True, score is multiplied by self-reported confidence
    (per ReConcile, arXiv 2309.13007 — reported +11.4% on reasoning benchmarks).
    """
    results = rollout.get("results", {})
    target_status = results.get(target_agent, "")
    base = {"PASS": 1.0, "CLEAN": 0.7, "FAIL": -1.0, "INCONCLUSIVE": 0.0}.get(
        target_status, 0.0
    )
    critic_status = results.get("critic", "")
    critic = 0.0
    if critic_status == "CLEAN":
        critic = 0.3
    elif critic_status.startswith("HAS_FINDINGS"):
        critic = -0.3
    raw = base * 0.7 + critic * 0.3

    if weight_by_confidence:
        confidence = extract_confidence(rollout)
        rollout["_confidence"] = confidence
        raw = raw * confidence

    return round(raw, 4)


def usc_pick(prompt: str, rollouts: list[dict], max_budget: float = 0.05) -> int:
    """Universal Self-Consistency: pick the rollout most consistent with the others.

    Reference: arXiv 2311.17311 (Chen et al. 2023). Falls back to score-argmax on error.
    """
    try:
        # Lazy import to keep main path clean
        sys.path.insert(0, str(Path(__file__).parent))
        import usc as usc_mod
    except ImportError:
        return -1

    candidates: list[str] = []
    for r in rollouts:
        jsonl = r.get("jsonl")
        text = ""
        if jsonl:
            try:
                for line in open(jsonl):
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("type") == "assistant":
                        for block in (evt.get("message") or {}).get("content", []) or []:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text += block.get("text", "") + "\n"
            except OSError:
                pass
        candidates.append(text[:3000] or f"<empty rollout {r.get('idx')}>")

    res = usc_mod.usc_pick(prompt, candidates, max_budget=max_budget)
    return res.get("idx", -1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("prompt")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-budget-usd", type=float, default=1.0)
    ap.add_argument(
        "--mode",
        choices=["critic", "usc", "confidence", "hybrid"],
        default="critic",
        help="critic = argmax(critic_score) [default], usc = Universal Self-Consistency, "
             "confidence = critic × self-reported confidence, hybrid = critic gates → USC tiebreaks",
    )
    args = ap.parse_args()

    if args.n < 2 or args.n > 8:
        print("[best-of-n] --n must be in [2, 8]", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else (RL_DIR / "best-of-n-runs" / timestamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[best-of-n] agent={args.agent} n={args.n} out={out_dir}", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.n) as ex:
        futures = [
            ex.submit(run_one, i, args.agent, args.prompt, out_dir, args.max_budget_usd)
            for i in range(args.n)
        ]
        rollouts = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Score and pick winner per mode
    weight_conf = args.mode in ("confidence", "hybrid")
    for r in rollouts:
        r["score"] = score_rollout(r, args.agent, weight_by_confidence=weight_conf)
    rollouts.sort(key=lambda r: r["score"], reverse=True)

    if args.mode == "usc":
        usc_idx = usc_pick(args.prompt, rollouts, max_budget=0.05)
        if usc_idx >= 0:
            # Find the rollout with that idx
            winner = next((r for r in rollouts if r["idx"] == usc_idx), rollouts[0])
        else:
            winner = rollouts[0]
    elif args.mode == "hybrid":
        # Critic-rank narrows to top-3 PASSing candidates; USC picks from those
        passing = [r for r in rollouts if r.get("score", 0) > 0]
        if len(passing) >= 2:
            usc_idx = usc_pick(args.prompt, passing[:3], max_budget=0.05)
            if usc_idx >= 0 and usc_idx < len(passing[:3]):
                winner = passing[:3][usc_idx]
            else:
                winner = rollouts[0]
        else:
            winner = rollouts[0]
    else:
        winner = rollouts[0]

    decision = {
        "ts": timestamp,
        "agent": args.agent,
        "mode": args.mode,
        "n": args.n,
        "rollouts": [
            {"idx": r["idx"], "score": r["score"], "results": r.get("results"),
             "confidence": r.get("_confidence"), "elapsed_s": r.get("elapsed_s"),
             "exit": r.get("exit")}
            for r in rollouts
        ],
        "chosen_idx": winner["idx"],
        "chosen_score": winner["score"],
    }
    (out_dir / "decision.json").write_text(json.dumps(decision, indent=2))

    # Symlink winner
    winner_link = out_dir / "winner.jsonl"
    try:
        if winner_link.exists() or winner_link.is_symlink():
            winner_link.unlink()
        winner_link.symlink_to(Path(winner["jsonl"]).name)
    except OSError:
        pass

    # Emit a reward event for this best-of-n decision
    reward_rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": args.agent, "source": "best_of_n",
        "signal": "best_of_n_decision", "reward": winner["score"],
        "n": args.n, "spread": round(rollouts[0]["score"] - rollouts[-1]["score"], 4),
        "out_dir": str(out_dir),
    }
    (RL_DIR / "rewards.jsonl").open("a").write(json.dumps(reward_rec) + "\n")

    # Print decision to stdout for the caller
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
