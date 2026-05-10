# RL Layer — Reward, Preferences, Value, Policy

Online learning infrastructure for the agent fleet. Inspired by RLHF/DPO patterns
adapted for prompt-based agents (no fine-tuning, no gradient updates — just
reward-aware policy/prompt evolution).

## Components

```
~/.claude/rl/
├── rewards.jsonl         # append-only reward events (one event per line)
├── preferences.jsonl     # (chosen, rejected) pairs for DPO-style preference data
├── value/<agent>.json    # per-agent rolling reward statistics (V-function approx)
├── policy/<agent>/       # current + candidate prompt versions + history
│   ├── current -> ~/.claude/agents/<agent>.md   (symlink to live agent)
│   ├── candidates/       # A/B variants under test
│   └── history/          # archived versions tagged with reward stats
├── scenarios/            # held-out scenarios for A/B comparison
└── _scripts/             # internal scripts (emit_*, best_of_n, ab_test)
```

## Reward Sources

| Signal | Source | Reward |
|---|---|---|
| Verifier PASS | TaskCompleted hook reads RESULT_verifier= | +1.0 |
| Verifier FAIL | same | -1.0 |
| Verifier INCONCLUSIVE | same | 0.0 |
| Critic CLEAN | RESULT_critic=CLEAN parsed | +0.5 |
| Critic CRITICAL/HIGH finding | parsed from session | -0.5 per finding (cap -2) |
| User correction | UserPromptSubmit hook detects negation patterns | -2.0 |
| Eval pass | /eval scenario PASS | +0.5 per criterion (weighted) |
| Eval fail | /eval scenario FAIL | -1.0 |
| Session anomaly (cache <70%) | SessionEnd | -0.3 |
| Task-level cost overrun (>2x p50) | TaskCompleted | -0.2 |

## Reward Event Schema

Every line of `rewards.jsonl`:
```json
{
  "ts": "2026-05-10T14:35:00Z",
  "session_id": "abc-123",
  "task_id": "task-7",                    // optional
  "agent": "verifier",                    // which agent earned the signal
  "source": "task_completed",             // task_completed | correction | session_end | eval | critic
  "signal": "verifier_pass",
  "reward": 1.0,
  "evidence": "RESULT_verifier=PASS",
  "model": "claude-sonnet-4-6",
  "cost_usd": 0.05
}
```

## Preference Pair Schema

Every line of `preferences.jsonl`:
```json
{
  "ts": "...",
  "agent": "verifier",
  "task_context": "<task description, ≤500 chars>",
  "chosen": {"text": "<the user-approved or PASS output>", "reward": 1.0},
  "rejected": {"text": "<the corrected/failed output>", "reward": -1.0},
  "source_session": "abc-123"
}
```

## Value Function (V-approximation)

`value/<agent>.json`:
```json
{
  "agent": "verifier",
  "n_runs": 142,
  "mean_reward": 0.73,
  "stderr": 0.08,
  "rolling_7d": {"n": 28, "mean": 0.81, "stderr": 0.12},
  "rolling_30d": {"n": 89, "mean": 0.69, "stderr": 0.10},
  "by_task_type": {
    "code_change": {"n": 60, "mean": 0.85},
    "config_change": {"n": 22, "mean": 0.55}
  },
  "last_updated": "2026-05-10T14:35:00Z"
}
```

Used to:
- Rank agents for /tune-agent priority (lowest mean reward → tune first)
- Detect regressions (drop in rolling_7d vs rolling_30d > 1 stderr → flag)
- Choose between candidate prompts (highest mean wins promotion)

## Policy Update Mechanism (no fine-tuning)

We do not update model weights. Policy = prompt. Updates flow:

1. **Trigger**: agent-tuner (Reflexion) detects ≥2 failures of same class on same agent
2. **Propose**: agent-tuner writes candidate at `policy/<agent>/candidates/<ts>-<n>.md`
3. **A/B**: `/ab-test <agent>` runs current vs candidate against held-out scenarios
4. **Decide**: if candidate's mean_reward > current's by >1 stderr (and n ≥ 10), promote
5. **Promote**: backup current to `history/<ts>.md`, replace agent file with candidate
6. **Continue measuring**: rewards keep flowing in; if regression detected, can rollback

## Best-of-N (Test-Time Scaling)

For high-stakes invocations (verifier on a release-blocking change), run the agent
N times in parallel, score each with the critic, pick the highest-scored output.

```
/best-of-n verifier "..." --n 3
```

## Skills

- `/rl-status [agent]` — show value-function snapshot + recent reward trend
- `/best-of-n <agent> <prompt>` — N-sample with critic ranking
- `/ab-test <agent>` — run candidate vs current on scenarios; promote winner
- `/eval-author <target>` — generate scenario stubs from past good runs
- `/apply-mining-patches <run-ts>` — apply approved trajectory-mining diffs

## Hook Wiring

| Event | Hook | What it emits |
|---|---|---|
| TaskCompleted | verify-gate.sh + emit_task_reward.py | reward event |
| UserPromptSubmit | emit_correction_signal.py | correction reward (negative) |
| SessionEnd | log-cache-stats.sh + emit_session_rewards.py | session-level reward + value update |

## Anti-Patterns

- **Reward hacking**: an agent learns to skip work to avoid critic findings. Mitigation: verifier reward dominates; can't get +1 without actual PASS evidence.
- **Sparse signal**: many tasks have no clear reward. We log a small +0.1 per "task closed without correction" as a baseline positive.
- **Policy drift**: candidate promoted on small sample. Mitigation: minimum n=10 with stderr gating before promotion.
- **Stale value estimates**: agent-tuner patches but value function reflects old prompt. Mitigation: on promotion, value reset to "warmup" mode that requires 5 runs before making policy decisions.
