#!/usr/bin/env python3
"""
Universal Self-Consistency (USC) aggregator for best-of-N.

Reference: Chen et al. 2023, arXiv 2311.17311 — "Universal Self-Consistency for
Large Language Model Generation".

Idea: instead of picking the candidate with highest critic score (argmax),
concatenate the N candidates and ask Claude itself to pick the one MOST CONSISTENT
with the others. Works on free-form output where no parseable answer exists.

Used by best_of_n.py when --mode=usc or --mode=hybrid.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def claude_flags(max_budget: float = 0.05) -> list[str]:
    base = [
        "-p",
        "--output-format", "json",
        "--max-turns", "1",
        "--max-budget-usd", str(max_budget),
        "--no-session-persistence",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + ["--setting-sources", "user", "--exclude-dynamic-system-prompt-sections"]


USC_PROMPT = """You are an output consistency judge. I will give you {n} candidate responses to the same prompt. Your job is to identify the response most consistent with the others — the one that captures what the majority of candidates AGREE on.

DO NOT evaluate which is best stylistically. Pick the response that, if all candidates were polled, would be closest to the consensus.

If candidates disagree substantially on key points, pick the response with reasoning supported by the most other candidates.

Output ONLY a single integer 1..{n} indicating the chosen candidate number. No explanation. No preamble.

PROMPT WAS:
{prompt}

CANDIDATES:
{candidates}
"""


def usc_pick(prompt: str, candidates: list[str], max_budget: float = 0.05) -> dict:
    """Ask Claude to pick the most consistent candidate. Returns {idx, raw}."""
    if not candidates:
        return {"idx": -1, "raw": "no candidates"}
    if len(candidates) == 1:
        return {"idx": 0, "raw": "only one candidate"}

    formatted = "\n\n".join(
        f"=== CANDIDATE {i+1} ===\n{c[:3000]}" for i, c in enumerate(candidates)
    )
    full_prompt = USC_PROMPT.format(
        n=len(candidates),
        prompt=prompt[:1500],
        candidates=formatted,
    )

    try:
        proc = subprocess.run(
            ["claude"] + claude_flags(max_budget=max_budget),
            input=full_prompt,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"idx": -1, "raw": "timeout"}

    raw = proc.stdout.strip()
    # Output format json gives {"result": "..."}
    try:
        parsed = json.loads(raw)
        result_text = parsed.get("result", "") if isinstance(parsed, dict) else str(parsed)
    except json.JSONDecodeError:
        result_text = raw

    # Extract first integer from result
    import re
    m = re.search(r"\b(\d+)\b", result_text)
    if not m:
        return {"idx": -1, "raw": result_text[:200]}

    chosen = int(m.group(1)) - 1  # 1-indexed → 0-indexed
    if not 0 <= chosen < len(candidates):
        return {"idx": -1, "raw": f"out of range: {chosen+1}/{len(candidates)}"}

    return {"idx": chosen, "raw": result_text[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True, help="The original prompt")
    ap.add_argument("--candidates-file", required=True,
                    help="JSON file containing list of candidate strings")
    ap.add_argument("--max-budget-usd", type=float, default=0.05)
    args = ap.parse_args()

    candidates = json.loads(Path(args.candidates_file).read_text())
    result = usc_pick(args.prompt, candidates, max_budget=args.max_budget_usd)
    print(json.dumps(result, indent=2))
    return 0 if result["idx"] >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
