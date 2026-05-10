---
name: best-of-n
description: Run an agent N times in parallel against the same prompt, score each output with the critic, return the best. Use for high-stakes invocations where you'd rather pay 3x to be sure (release-blocking verifier runs, security review of sensitive code). Triggers on /best-of-n, "best of n", "run multiple", "give me three options".
when_to_use: When the cost of being wrong > 3x the cost of running. Verifier on a critical fix. Security review on auth code. Migration plan for production DB. Use sparingly.
allowed-tools: Bash, Read
arguments: [agent, prompt, n]
---

# /best-of-n — Test-time scaling via parallel agent rollouts

`/best-of-n <agent> "<prompt>" [n=3]` runs the named agent N times in parallel, scores each rollout via parsed `RESULT_<agent>=` lines (and critic where applicable), and returns the highest-scoring output.

This is **test-time RL**: instead of trusting one rollout, sample many and pick by reward. Cost scales linearly with N.

## How

```bash
python3 ~/.claude/rl/best_of_n.py <agent> "<prompt>" --n <N>
```

`<N>` must be in [2, 8]. Default 3.

The runner:
1. Spawns N parallel `claude -p` invocations, each prefixed "Use the <agent> agent for this. <prompt>"
2. Each rollout writes its full stream-json transcript to `~/.claude/rl/best-of-n-runs/<ts>/run-<i>.jsonl`
3. Parses `RESULT_<agent>=` lines from each rollout
4. Scores: PASS=+1, CLEAN=+0.7, FAIL=-1, INCONCLUSIVE=0; with critic delta if present
5. Picks the highest-scoring rollout; symlinks `winner.jsonl`
6. Writes `decision.json` with all rollout scores
7. Emits a single reward event for the decision

## Output

```json
{
  "agent": "verifier",
  "n": 3,
  "rollouts": [
    {"idx": 1, "score": 1.0, "results": {"verifier": "PASS"}, "elapsed_s": 12.4},
    {"idx": 2, "score": 1.0, "results": {"verifier": "PASS"}, "elapsed_s": 14.1},
    {"idx": 0, "score": -1.0, "results": {"verifier": "FAIL"}, "elapsed_s": 18.3}
  ],
  "chosen_idx": 1,
  "chosen_score": 1.0,
  "spread": 2.0
}
```

If `spread` is large (>0.5), this means rollouts disagreed — useful diagnostic. Trust the winner less in that case; consider going to N=5.

## When NOT to use

- Routine task closure — overkill
- When the agent is deterministic-by-design (linter wrappers, doc generators)
- When budget is tight — N rollouts cost ~N× a single
- When you don't have a clear `RESULT_<agent>=` last line — scoring degrades to 0

## Anti-patterns

- Calling `/best-of-n` on the wrapping skill (e.g., `/best-of-n verify ...`) — call on the agent (`/best-of-n verifier ...`)
- Setting N=8 by default — wastes cost. Default 3 is a strong baseline.
- Trusting the winner without reading its evidence — even the best of 3 can be wrong; this is not a substitute for review.
- Calling on agents that don't emit `RESULT_<name>=` lines — score is meaningless without that contract.
