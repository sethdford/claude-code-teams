#!/usr/bin/env python3
"""
AggAgent — synthesize a single final answer across N parallel rollouts.

Reference: arXiv:2604.11753 "Agentic Aggregation" (2026). Instead of best-of-N's
argmax-picks-one approach, treat the N rollouts as an environment and ask the
model to synthesize a single answer that captures consensus + best divergences
+ unique insights from each candidate.

Reported gain: +5.3% average, +10.3% on deep research, ≤1 extra rollout overhead.

Different from USC (Universal Self-Consistency, arXiv 2311.17311):
  - USC PICKS the most consistent rollout (returns idx)
  - AggAgent SYNTHESIZES a new answer combining all (returns new text)

Same cost: N + 1 model calls.

Usage:
  aggagent.py --prompt "..." --candidates-file rollouts.json --max-budget-usd 0.10

Used by best_of_n.py when --mode=synthesize.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def claude_flags(max_budget: float = 0.10) -> list[str]:
    base = [
        "-p",
        "--output-format", "json",
        "--max-turns", "1",
        "--max-budget-usd", str(max_budget),
        "--no-session-persistence",
    ]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ["--bare"] + base
    return base + [
        "--setting-sources", "user",
        "--exclude-dynamic-system-prompt-sections",
    ]


SYNTH_PROMPT = """You are a SYNTHESIS agent. I will give you {n} candidate responses to the same task. Your job is NOT to pick one — your job is to produce a SINGLE FINAL ANSWER that combines the best insights from all of them.

Method:
1. **Agreement**: identify what all (or most) candidates agree on. Treat this as high-confidence baseline.
2. **Divergence**: where candidates differ, decide which approach is correct (or combine if they're complementary).
3. **Unique insights**: any candidate that contributed something the others missed — preserve it.
4. **Synthesize**: produce a final answer that incorporates 1+2+3.

Your output must have THREE sections in this exact order:

```
## AGREEMENT
- <bullet>
- <bullet>

## DIVERGENCE_DECISIONS
- On <topic>, candidate <n> said X; candidate <m> said Y. I picked X because <reason>.
- ...

## SYNTHESIZED_FINAL_ANSWER
<the actual combined answer — this is what gets used downstream>
```

Critical:
- The SYNTHESIZED_FINAL_ANSWER section must stand alone — it should make sense without reading the candidates.
- Do not just paraphrase one candidate. If you find yourself doing that, you missed an insight from the others.
- If candidates contradict on a fact, pick the one with strongest justification. Note the conflict.
- If you cannot synthesize (candidates too divergent), say so explicitly — don't fabricate consensus.

ORIGINAL TASK:
{prompt}

CANDIDATES:
{candidates}
"""


def synthesize(
    prompt: str, candidates: list[str], max_budget: float = 0.10
) -> dict:
    """Synthesize a single answer across N rollouts.

    Returns:
        {
            "synthesized": "<final answer text>",
            "agreement": ["<bullet>", ...],
            "divergences": ["<decision>", ...],
            "raw": "<full model output>",
            "n_candidates": N,
            "error": "<error message if any>"
        }
    """
    if not candidates:
        return {"synthesized": "", "error": "no candidates", "n_candidates": 0}
    if len(candidates) == 1:
        return {
            "synthesized": candidates[0],
            "agreement": [],
            "divergences": [],
            "raw": candidates[0],
            "n_candidates": 1,
            "note": "single candidate; returned as-is (no synthesis needed)",
        }

    # Truncate each candidate to keep total context manageable
    formatted = "\n\n".join(
        f"=== CANDIDATE {i + 1} ===\n{c[:4000]}" for i, c in enumerate(candidates)
    )
    full_prompt = SYNTH_PROMPT.format(
        n=len(candidates),
        prompt=prompt[:2000],
        candidates=formatted,
    )

    try:
        proc = subprocess.run(
            ["claude"] + claude_flags(max_budget=max_budget),
            input=full_prompt,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "synthesized": "",
            "error": "timeout",
            "n_candidates": len(candidates),
        }

    raw = proc.stdout.strip()

    # claude -p --output-format json wraps the result
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            if parsed.get("is_error"):
                return {
                    "synthesized": "",
                    "error": f"api_error_{parsed.get('api_error_status')}: {parsed.get('result', '')[:200]}",
                    "n_candidates": len(candidates),
                }
            text = parsed.get("result", "") or ""
        else:
            text = str(parsed)
    except json.JSONDecodeError:
        text = raw

    return parse_synthesis(text, n_candidates=len(candidates))


def parse_synthesis(text: str, n_candidates: int) -> dict:
    """Parse the structured 3-section response."""
    out: dict = {
        "raw": text,
        "n_candidates": n_candidates,
        "agreement": [],
        "divergences": [],
        "synthesized": "",
    }

    # Pull each section by header
    agreement_match = re.search(
        r"##\s*AGREEMENT\s*\n(.*?)(?=##\s*DIVERGENCE_DECISIONS|##\s*SYNTHESIZED_FINAL_ANSWER|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if agreement_match:
        out["agreement"] = [
            line.strip().lstrip("- ").lstrip("* ").strip()
            for line in agreement_match.group(1).strip().split("\n")
            if line.strip().startswith(("-", "*"))
        ]

    div_match = re.search(
        r"##\s*DIVERGENCE_DECISIONS\s*\n(.*?)(?=##\s*SYNTHESIZED_FINAL_ANSWER|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if div_match:
        out["divergences"] = [
            line.strip().lstrip("- ").lstrip("* ").strip()
            for line in div_match.group(1).strip().split("\n")
            if line.strip().startswith(("-", "*"))
        ]

    synth_match = re.search(
        r"##\s*SYNTHESIZED_FINAL_ANSWER\s*\n(.*)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if synth_match:
        out["synthesized"] = synth_match.group(1).strip()
    else:
        # Fallback: model didn't follow the format. Use the whole output.
        out["synthesized"] = text.strip()
        out["format_warning"] = "model did not emit the 3-section structure; raw text used as fallback"

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="AggAgent synthesis over N rollouts")
    ap.add_argument("--prompt", required=True, help="The original task prompt")
    ap.add_argument(
        "--candidates-file",
        required=True,
        help="JSON file containing list of candidate strings",
    )
    ap.add_argument("--max-budget-usd", type=float, default=0.10)
    ap.add_argument("--out", help="Optional path to write decision JSON")
    args = ap.parse_args()

    candidates = json.loads(Path(args.candidates_file).read_text())
    if not isinstance(candidates, list):
        print("[aggagent] candidates-file must contain a JSON array", file=sys.stderr)
        return 1

    result = synthesize(args.prompt, candidates, max_budget=args.max_budget_usd)

    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(out_text)
    print(out_text)

    return 0 if result.get("synthesized") else 1


if __name__ == "__main__":
    sys.exit(main())
