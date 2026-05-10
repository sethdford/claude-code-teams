---
name: aspect-panel
description: Run a panel of 5 specialized verifiers (correctness, edge-case, security, regression, style) in parallel against a change, with confidence-weighted voting. Disagreement (40-60% pass share) escalates to lead. Replaces single-critic for high-stakes review. Triggers on /aspect-panel, "panel review", "multi-aspect verify", "review with multiple critics".
when_to_use: Before merging release-blocking changes. Before committing security-sensitive code. After /verify says PASS but you want orthogonal coverage. NOT for trivial diffs (use /verify alone).
allowed-tools: Bash, Read
arguments: [target]
---

# /aspect-panel — Heterogeneous Verifier Panel

`/aspect-panel <target>` spawns 5 aspect-specialized verifiers in parallel, each examining one dimension of the change. Confidence-weighted vote produces a final verdict; disagreement is preserved as a signal.

Built on:
- Lifshitz et al. 2025 — Multi-Agent Verification (MAV)
- arXiv [2510.01499](https://arxiv.org/abs/2510.01499) — "Beyond Majority Voting"
- arXiv [2308.07201](https://arxiv.org/abs/2308.07201) — ChatEval (heterogeneous personas matter)

## How

```bash
python3 ~/.claude/rl/aspect_panel.py --target "<files-or-diff-or-description>"
```

The script:
1. Spawns 5 aspect verifiers in parallel via `claude -p`:
   - **correctness-verifier** — does the change implement the contract?
   - **edge-case-verifier** — NULL/empty/overflow/concurrent inputs handled?
   - **security-verifier** — paranoid OWASP/secrets/injection sweep
   - **regression-verifier** — what existing behavior could this break?
   - **style-verifier** — maintainability, hates clever code
2. Each emits `VERDICT: pass|fail`, `CONFIDENCE: 0.0-1.0`, `RATIONALE`, and `RESULT_<aspect>-verifier=PASS|FAIL`.
3. Aggregator computes confidence-weighted vote:
   - `pass_share = sum(conf where pass) / sum(conf)`
   - `pass_share > 0.6` → **PASS**
   - `pass_share < 0.4` → **FAIL**
   - `0.4 ≤ pass_share ≤ 0.6` → **ESCALATE** (real disagreement; surface to lead)

## Output

```json
{
  "ts": "...",
  "target": "...",
  "aspects": [
    {"aspect": "correctness", "verdict": "pass", "confidence": 0.85, "rationale": "..."},
    {"aspect": "edge-case", "verdict": "fail", "confidence": 0.72, "rationale": "no handling for None input at src/x.py:42"},
    ...
  ],
  "aggregate": {
    "verdict": "ESCALATE",
    "pass_share": 0.55,
    "split": true
  }
}
```

A reward event is emitted to `~/.claude/rl/rewards.jsonl` recording the panel's decision.

## When to use which

| Stake | Use |
|---|---|
| Trivial change (rename, format, comment) | nothing, or `/verify` |
| Routine task closure | `/verify` (single verifier) |
| Pre-commit on a touched-shared-code change | `/verify` + `/aspect-panel` |
| Release-blocking, security-sensitive, migration | `/aspect-panel` + `/best-of-n verifier --n 3` |

The panel costs ~5× a single `/verify` (5 parallel verifiers). Don't run for free.

## Why heterogeneous personas matter

ChatEval (2308.07201) found **homogeneous personas hurt** — running 5 identical critics adds noise without signal. Each verifier in our panel has a deliberately different priority: paranoid security vs perf vs maintainability. They catch different bug classes.

The ESCALATE state when they disagree is itself the signal: when 50/50 split, you don't have consensus, and pretending to is worse than admitting it.

## Anti-patterns to refuse

- Running on a 5-line diff (overkill; the cost dominates the benefit)
- Auto-resolving ESCALATE without surfacing to lead (defeats the design)
- Using only one or two aspects (the value is in coverage breadth — run all 5)
- Treating confidence values as ground truth (they're self-reported; use as a weight, not as truth)
