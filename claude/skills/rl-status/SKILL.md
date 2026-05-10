---
name: rl-status
description: Show the RL value-function snapshot for all agents — mean reward, recent trend, anomalies, top tuning candidates. Use weekly to monitor agent quality. Triggers on /rl-status, "agent rewards", "rl status", "which agents are degrading".
when_to_use: Weekly review. After /mine-transcripts. When investigating "why is X agent making mistakes lately". Before deciding to /tune-agent.
allowed-tools: Bash, Read
---

# /rl-status — Agent Reward & Value Snapshot

Shows the per-agent reward trajectory built up by the RL hooks (`emit_task_reward`, `emit_correction_signal`, `emit_session_rewards`).

## Output

```
# RL Status — <date>

## Agent value table (sorted by 7d mean, ascending = worst first)
| Agent | n_total | mean (all) | 7d n | 7d mean | 7d-30d delta | trend |
|---|---|---|---|---|---|---|
| flake-detector | 18 | 0.42 | 5 | -0.20 | ↓ -0.62 | DEGRADING |
| verifier | 142 | 0.81 | 28 | 0.85 | ↑ +0.04 | stable |
...

## Anomalies (last 7d)
- 3 sessions with cache hit rate below 70%
- 2 corrections matched against `agent-tuner` (false positives?)

## Top tuning candidates (≥2 negative occurrences from same agent)
1. flake-detector — 4 verifier_fail in 7d. Run `/tune-agent flake-detector`.
2. ...

## Recent reward distribution (24h)
{ verifier_pass: 12, verifier_fail: 1, critic_clean: 8, critic_findings: 3, correction_detected: 2 }
```

## How

```bash
# Read all value snapshots
ls ~/.claude/rl/value/*.json | xargs -I {} cat {} | jq -s 'sort_by(.rolling_7d.mean)'

# Reward histogram
jq -s 'group_by(.signal) | map({signal: .[0].signal, n: length, mean_reward: ([.[] | .reward] | add / length)})' \
  ~/.claude/rl/rewards.jsonl

# Recent corrections (24h)
python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta
cutoff = datetime.now(timezone.utc) - timedelta(days=1)
for line in open('$HOME/.claude/rl/rewards.jsonl'):
    r = json.loads(line)
    ts = datetime.fromisoformat(r['ts'].replace('Z','+00:00'))
    if ts > cutoff and r.get('source') == 'user_correction':
        print(r['agent'], '—', r.get('matched_pattern',''))
"
```

## Tuning candidate criteria

An agent appears as a tuning candidate when:
- `rolling_7d.mean < 0` (more failures than successes recently), OR
- `rolling_7d.mean - rolling_30d.mean < -0.3` (sharp drop), OR
- ≥2 verifier_fail OR correction_detected events from this agent in 7d

Surface these with the recommended `/tune-agent <name>` command.

## What this is NOT

- Real fine-tuning (we only adjust prompts via Reflexion)
- Statistical-significance-tested A/B results (use `/ab-test` for that)
- Cost reporting (use `/cache-report`)

This is operational telemetry for "is the fleet healthy?"
