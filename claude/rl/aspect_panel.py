#!/usr/bin/env python3
"""
Aspect-Verifier Panel — replaces single critic with N specialized verifiers
running in parallel, confidence-weighted vote.

References:
- Lifshitz et al. 2025 — Multi-Agent Verification (MAV)
- arXiv 2510.01499 — "Beyond Majority Voting" (confidence-weighted aggregation)
- arXiv 2308.07201 — ChatEval (heterogeneous personas matter; homogeneous hurt)

Aspect verifiers (5 default panels — heterogeneous personas):
  correctness-verifier  — does the change do what was asked?
  edge-case-verifier    — what happens at NULL/empty/overflow/concurrent?
  security-verifier     — OWASP top 10, secrets, injection, traversal
  regression-verifier   — what existing behavior might this break?
  style-verifier        — naming, idioms, project conventions

Each emits {verdict: pass|fail, confidence: 0-1, rationale}. Final aggregation
is confidence-weighted vote with disagreement-as-signal.

Usage:
  aspect_panel.py --target <files-or-diff> [--aspects <list>] [--out <dir>]
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

DEFAULT_ASPECTS = [
    "correctness",
    "edge-case",
    "security",
    "regression",
    "style",
]

ASPECT_PROMPTS = {
    "correctness": """You are a correctness verifier. Read the change at {target} and answer ONE question: does this change correctly implement what the contract asked for?

Look for: missing branches, off-by-one, inverted logic, wrong type returned, contract not satisfied.

Output strictly:
VERDICT: pass | fail
CONFIDENCE: 0.0 - 1.0 (how sure you are; 0.5 means could go either way)
RATIONALE: <1-2 sentences with file:line evidence>

Last line: RESULT_correctness-verifier=PASS|FAIL""",

    "edge-case": """You are an edge-case verifier. Read the change at {target} and answer ONE question: are the inputs that COULD break this code handled?

Look for: NULL/None/undefined inputs, empty collections, integer overflow, floating-point precision, concurrent access, resource exhaustion, malformed input.

Output strictly:
VERDICT: pass | fail
CONFIDENCE: 0.0 - 1.0
RATIONALE: <1-2 sentences naming a SPECIFIC edge case that is/isn't handled>

Last line: RESULT_edge-case-verifier=PASS|FAIL""",

    "security": """You are a paranoid security verifier. Read the change at {target} and answer ONE question: does this introduce a security issue?

Look for: hardcoded secrets, SQL/command/template injection, SSRF, path traversal, weak crypto (MD5/SHA1, ECB, no salt), unsafe deserialization, missing auth on routes, PII in logs, open redirect.

Output strictly:
VERDICT: pass | fail
CONFIDENCE: 0.0 - 1.0
RATIONALE: <1-2 sentences with the specific vulnerability if any>

Last line: RESULT_security-verifier=PASS|FAIL""",

    "regression": """You are a regression verifier. Read the change at {target} and answer ONE question: what existing behavior could this break?

Look for: API signature changes, removed parameters, changed defaults, modified shared utilities, schema changes affecting other queries, removed error paths.

Output strictly:
VERDICT: pass | fail
CONFIDENCE: 0.0 - 1.0
RATIONALE: <1-2 sentences naming the at-risk caller or behavior, if any>

Last line: RESULT_regression-verifier=PASS|FAIL""",

    "style": """You are a maintainability/style verifier — but you HATE clever code. Read the change at {target} and answer ONE question: will another engineer understand this in six months?

Look for: god functions, magic numbers, unclear names, dead code, comments that explain WHAT instead of WHY, abstractions invented for hypothetical futures, unnecessary indirection.

Output strictly:
VERDICT: pass | fail
CONFIDENCE: 0.0 - 1.0
RATIONALE: <1-2 sentences>

Last line: RESULT_style-verifier=PASS|FAIL""",
}


def claude_flags(max_budget: float = 0.10) -> list[str]:
    base = [
        "-p",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--max-turns", "5",
        "--max-budget-usd", str(max_budget),
        "--allowedTools", "Read,Glob,Grep,Bash",
        "--no-session-persistence",
        "--verbose",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + ["--setting-sources", "user", "--exclude-dynamic-system-prompt-sections"]


def run_aspect(aspect: str, target: str, out_dir: Path) -> dict:
    """Run one aspect verifier. Returns {aspect, verdict, confidence, rationale, raw}."""
    if aspect not in ASPECT_PROMPTS:
        return {"aspect": aspect, "verdict": "error", "confidence": 0.0, "rationale": "unknown aspect"}

    prompt = ASPECT_PROMPTS[aspect].format(target=target)
    log = out_dir / f"{aspect}.jsonl"
    stderr = out_dir / f"{aspect}.stderr"

    start = time.time()
    try:
        with log.open("w") as out_f, stderr.open("w") as err_f:
            proc = subprocess.run(
                ["claude"] + claude_flags(),
                input=prompt, text=True, stdout=out_f, stderr=err_f,
                timeout=120, check=False,
            )
        elapsed = time.time() - start
    except subprocess.TimeoutExpired:
        return {"aspect": aspect, "verdict": "timeout", "confidence": 0.0, "rationale": "subprocess timeout"}

    # Parse the verifier output from stream-json
    try:
        text = log.read_text()
    except OSError:
        text = ""

    # Find the assistant text content
    full_text = ""
    for line in text.splitlines():
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "assistant":
            for block in (evt.get("message") or {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    full_text += block.get("text", "") + "\n"

    verdict = "unknown"
    confidence = 0.5
    rationale = ""

    m = re.search(r"VERDICT:\s*(pass|fail)", full_text, re.IGNORECASE)
    if m:
        verdict = m.group(1).lower()
    m = re.search(r"CONFIDENCE:\s*([\d.]+)", full_text)
    if m:
        try:
            confidence = max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass
    m = re.search(r"RATIONALE:\s*(.+?)(?=\n|RESULT_|$)", full_text, re.DOTALL)
    if m:
        rationale = m.group(1).strip()[:300]

    # Cross-check with RESULT_ line
    m = re.search(r"RESULT_[\w-]+=(PASS|FAIL)", full_text)
    if m and verdict == "unknown":
        verdict = m.group(1).lower()

    return {
        "aspect": aspect,
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "elapsed_s": round(elapsed, 2),
    }


def aggregate(results: list[dict]) -> dict:
    """Confidence-weighted vote. Disagreement → ESCALATE."""
    pass_weight = sum(r["confidence"] for r in results if r["verdict"] == "pass")
    fail_weight = sum(r["confidence"] for r in results if r["verdict"] == "fail")
    total_weight = pass_weight + fail_weight

    if total_weight == 0:
        return {"verdict": "INCONCLUSIVE", "pass_weight": 0, "fail_weight": 0, "split": False}

    pass_share = pass_weight / total_weight
    # Disagreement signal: if pass_share is in [0.4, 0.6], it's a real split
    split = 0.4 <= pass_share <= 0.6

    if split:
        verdict = "ESCALATE"
    elif pass_share > 0.5:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "pass_weight": round(pass_weight, 3),
        "fail_weight": round(fail_weight, 3),
        "pass_share": round(pass_share, 3),
        "split": split,
    }


def emit_reward(decision: dict, target: str) -> None:
    rl_dir = Path.home() / ".claude" / "rl"
    rl_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verdict = decision["aggregate"]["verdict"]
    reward = {"PASS": 0.7, "FAIL": -0.7, "ESCALATE": 0.0, "INCONCLUSIVE": 0.0}.get(verdict, 0.0)
    rec = {
        "ts": ts,
        "agent": "aspect-panel",
        "source": "aspect_panel",
        "signal": f"panel_{verdict.lower()}",
        "reward": reward,
        "target_excerpt": target[:200],
        "pass_share": decision["aggregate"].get("pass_share"),
    }
    with (rl_dir / "rewards.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="Files, diff range, or description")
    ap.add_argument("--aspects", nargs="+", default=DEFAULT_ASPECTS,
                    choices=list(ASPECT_PROMPTS.keys()))
    ap.add_argument("--out", default=None, help="Output directory")
    args = ap.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else (
        Path.home() / ".claude" / "rl" / "aspect-panel-runs" / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[aspect-panel] target={args.target} aspects={args.aspects}", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.aspects)) as ex:
        futures = [ex.submit(run_aspect, a, args.target, out_dir) for a in args.aspects]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    results.sort(key=lambda r: r["aspect"])  # deterministic order for output
    aggregate_decision = aggregate(results)

    decision = {
        "ts": timestamp,
        "target": args.target,
        "aspects": results,
        "aggregate": aggregate_decision,
    }
    (out_dir / "decision.json").write_text(json.dumps(decision, indent=2))

    emit_reward(decision, args.target)

    print(json.dumps(decision, indent=2))
    return 0 if aggregate_decision["verdict"] in ("PASS", "ESCALATE") else 1


if __name__ == "__main__":
    sys.exit(main())
