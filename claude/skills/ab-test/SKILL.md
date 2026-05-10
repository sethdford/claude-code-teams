---
name: ab-test
description: A/B test an agent's current prompt against a candidate variant from policy/<agent>/candidates/. Runs both on the same scenarios, aggregates rewards, recommends promotion if candidate beats current by >1 stderr with n≥10. Triggers on /ab-test, "compare prompts", "test the candidate", "is the new prompt better".
when_to_use: After agent-tuner produces a candidate. After manual prompt edits to a high-traffic agent. Periodically to detect drift.
allowed-tools: Bash, Read, Edit, Write
arguments: [agent]
---

# /ab-test — Prompt variant A/B with reward gating

`/ab-test <agent> [--candidate <path>] [--runs <k>] [--promote <name>]` compares current vs candidate prompts on held-out scenarios and either promotes the winner or surfaces inconclusive.

## How

```bash
# Run A/B (reads candidates from policy/<agent>/candidates/)
python3 ~/.claude/rl/ab_test.py <agent> --runs 3

# Promote a named candidate (after reviewing the decision.json)
python3 ~/.claude/rl/ab_test.py <agent> --promote <candidate-name>
```

The runner:
1. For each scenario in `~/.claude/evals/scenarios/<agent>/`, runs the scenario `<runs>` times against the live agent prompt.
2. Same for each candidate in `~/.claude/rl/policy/<agent>/candidates/*.md`.
3. Aggregates per variant: `n`, `mean reward`, `stderr`.
4. Promotion rule: candidate's mean > current's mean + max(current.stderr, 0.05) AND n ≥ 10.
5. Writes `decision.json` and prints it.

## Output

```json
{
  "agent": "verifier",
  "scenarios": ["happy-path", "ambiguous-contract", "no-tests-exist"],
  "runs_per_scenario": 3,
  "current": {"n": 9, "mean": 0.78, "stderr": 0.12},
  "candidates": {
    "tuner-2026-05-10": {"n": 9, "mean": 0.92, "stderr": 0.08}
  },
  "winner": "tuner-2026-05-10",
  "promote": true,
  "promote_command": "python3 ~/.claude/rl/ab_test.py verifier --promote tuner-2026-05-10"
}
```

If `promote: true`, the user runs the command to apply. The previous live agent is archived to `policy/<agent>/history/<ts>.md`.

## Cost

A typical /ab-test runs `scenarios × runs × (1 + candidates)` claude invocations. For 5 scenarios × 3 runs × 2 variants (current + 1 candidate) = 30 calls. With the budget cap (`--max-budget-usd 0.3` per call), worst case ~$10. Run when it matters; don't run nightly.

## When NOT to use

- No held-out scenarios authored — `/ab-test` returns immediately with an error. Author scenarios via `/eval-author <agent>` first.
- Candidate prompt is identical to current — useless.
- Sample size will be too small (e.g., 1 scenario × 1 run) — no statistical power. Need n ≥ 10 for promotion.

## Anti-patterns

- Promoting after a single run — too noisy. Always run `/ab-test` and let the promotion rule gate.
- Running A/B with scenarios that exclusively tested the *current* prompt's strengths — selection bias. Mix scenarios.
- Promoting on `mean` alone without checking `stderr` — high variance candidates often regress later.
