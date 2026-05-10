---
name: cache-report
description: Show prompt cache hit rate trends and flag regressions. Use when user asks about cache performance, asks why sessions feel expensive, or wants to verify cache health. Triggers on /cache-report, "cache hit rate", "cache stats", "is caching working".
when_to_use: Weekly review, after a session that felt slow/expensive, when investigating cost spikes, after CLAUDE.md or rules edits (cache invalidation risk).
allowed-tools: Bash, Read
---

# /cache-report — Prompt Cache Hit Rate Health Check

Anthropic declares SEVs internally when cache hit rate drops. We do the same — except instead of paging, we surface a report.

## What you produce

A markdown report covering:

1. **Last 7 days** — avg hit rate, p50, p10 (worst sessions), trend vs previous 7 days
2. **Last 24 hours** — same, more granular
3. **By model** — Opus vs Sonnet vs Haiku breakdown
4. **Anomalies** — sessions where hit rate dropped below 70% (logged in `cache-anomalies.jsonl`)
5. **Top 3 expensive sessions** — by total cost; root-cause hypothesis for each
6. **Top 3 cache-cold sessions** — sessions with high cache_creation but low cache_read; identify why (new CLAUDE.md? new ruleset? clean compact?)

## How to compute

Read `~/.claude/telemetry/cache-stats.jsonl`. Each line is a session-end record:

```json
{"ts": "...", "session_id": "...", "model": "claude-opus-4-7", "input_tokens": 12345, "cache_read_tokens": 89012, "cache_creation_tokens": 3456, "cache_hit_rate": 0.85, "cost_usd": 1.23, ...}
```

Aggregate with `jq` or python. Don't load the whole file into Claude's context — process via shell, summarize.

```bash
# Quick averages
python3 -c "
import json, statistics
from datetime import datetime, timedelta, timezone
recs = [json.loads(l) for l in open('$HOME/.claude/telemetry/cache-stats.jsonl')]
now = datetime.now(timezone.utc)
def parse_ts(r):
    return datetime.fromisoformat(r['ts'].replace('Z','+00:00'))
last7 = [r for r in recs if (now - parse_ts(r)).days < 7]
last24 = [r for r in recs if (now - parse_ts(r)).total_seconds() < 86400]
def stats(rs):
    if not rs: return None
    rates = [r['cache_hit_rate'] for r in rs]
    costs = [r['cost_usd'] for r in rs]
    return {
      'n': len(rs),
      'mean_hit_rate': statistics.mean(rates),
      'p50_hit_rate': statistics.median(rates),
      'p10_hit_rate': sorted(rates)[max(0,len(rates)//10)],
      'total_cost_usd': sum(costs),
    }
print('7d:', stats(last7))
print('24h:', stats(last24))
"
```

## Threshold guidance

| Hit rate | Status | Action |
|---|---|---|
| ≥ 90% | Excellent | None |
| 80–90% | Healthy | None |
| 70–80% | Watch | Investigate top cold sessions |
| 60–70% | Degraded | Audit recent CLAUDE.md/rules edits, hook config |
| < 60% | Broken | Stop. Find what changed. SEV. |

## Common root causes for a drop

1. **CLAUDE.md edit** — invalidates the prefix until cache rebuilds (one or two sessions of cold cost is normal; sustained drop is a problem)
2. **New rule loaded** — same as above for `.claude/rules/*.md`
3. **MCP server churn** — added/removed servers changes tool descriptions
4. **`--bare` mode session that didn't populate cache** — expected for headless eval runs; filter these out
5. **Compaction without re-injection** — `SessionStart matcher: compact` hook missing or broken
6. **Skill content bloat** — invoking many skills mid-session can push old ones out

## Output format

```markdown
# Cache Report — <date>

## Headline
- 7d hit rate: 87% (↑ from 82% prior 7d)
- 24h hit rate: 91%
- Anomalies: 2 sessions below 70%

## By model
| Model | Sessions | Mean | P10 |
|---|---|---|---|
| opus | 42 | 89% | 72% |
| sonnet | 18 | 84% | 68% |

## Anomalies (24h)
- session=abc123: 64% hit rate, $4.21 cost. Likely cause: <hypothesis>
...

## Recommendations
- ...
```

Keep total report under 500 words. The data is the value, not the prose.
