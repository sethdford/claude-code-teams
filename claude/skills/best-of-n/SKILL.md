---
name: best-of-n
description: Run an agent N times in parallel against the same prompt, then aggregate via one of 5 modes — critic argmax, USC consistency, confidence-weighted, hybrid, or AggAgent synthesis. Use for high-stakes invocations where you'd rather pay Nx to be sure. Triggers on /best-of-n, "best of n", "run multiple", "give me three options", "synthesize across rollouts".
when_to_use: When the cost of being wrong > Nx the cost of running. Verifier on a critical fix. Security review on auth code. Migration plan for production DB. For deep-research-style tasks where rollouts have complementary insights, prefer --mode synthesize (AggAgent).
allowed-tools: Bash, Read
arguments: [agent, prompt, n, mode]
---

# /best-of-n — Test-time scaling via parallel agent rollouts

`/best-of-n <agent> "<prompt>" [n=3]` runs the named agent N times in parallel, scores each rollout via parsed `RESULT_<agent>=` lines (and critic where applicable), and returns the highest-scoring output.

This is **test-time RL**: instead of trusting one rollout, sample many and pick by reward. Cost scales linearly with N.

## How

```bash
python3 ~/.claude/rl/best_of_n.py <agent> "<prompt>" --n <N>
```

`<N>` must be in [2, 8]. Default 3.

## Aggregation modes

| `--mode` | What it does | Cost | When to use |
|---|---|---|---|
| `critic` (default) | argmax of critic-derived score | N calls | Routine high-stakes runs |
| `usc` | Universal Self-Consistency: pick the rollout most consistent with the others ([arXiv 2311.17311](https://arxiv.org/abs/2311.17311)) | N+1 calls | Free-form output where critic scores are noisy |
| `confidence` | Weight critic_score by self-reported confidence ([ReConcile, arXiv 2309.13007](https://arxiv.org/abs/2309.13007), +11.4%) | N calls | Agents that emit `CONFIDENCE: 0-1` lines |
| `hybrid` | Critic narrows to top-3 PASS, USC tiebreaks | N+1 calls | When critic discriminates well *and* you want consistency |
| `synthesize` | **AggAgent**: synthesize a NEW answer combining the best of all N rollouts ([arXiv 2604.11753](https://arxiv.org/abs/2604.11753), +5-10%) | N+1 calls | **Deep research, design docs, multi-step reasoning where rollouts have complementary insights** |

### When to pick `synthesize` over the others

Use `synthesize` when the task allows multiple correct approaches that complement each other (e.g., "design a system", "review this PR", "summarize these findings"). It treats N rollouts as parallel drafts and produces ONE merged final answer.

Use `critic` / `usc` / `confidence` / `hybrid` when there's exactly one right answer and you want to PICK from candidates rather than synthesize across them (e.g., "fix this specific bug", "produce this specific test").

The synthesizer emits a 3-section structured response:
- **AGREEMENT**: bullets of what most/all candidates agreed on
- **DIVERGENCE_DECISIONS**: per-divergence resolution with rationale
- **SYNTHESIZED_FINAL_ANSWER**: the merged output (this is what gets used downstream)

Output lands at `<out>/synthesized.txt` and `<out>/decision.json[synthesis]`.

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
