---
name: mine-transcripts
description: Mine past Claude Code session transcripts (JSONL) to extract user corrections, successful patterns, and recurring failure modes. Proposes diffs against lessons.md and rules/*.md for human review. Triggers on /mine-transcripts, "mine my sessions", "what did I learn this week", "session retro". Use weekly or after a fleet completes.
when_to_use: Weekly retro. After a fleet completes. When you suspect a pattern of mistakes. When CLAUDE.md feels stale.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
arguments: [since]
---

# /mine-transcripts — Turn past sessions into rule patches

`/mine-transcripts [since]` reads recent session JSONL files, extracts learnings, and proposes diffs.

## Defaults
- `since` defaults to `7d` (last 7 days)
- Other values: `24h`, `30d`, or an ISO date

## What you produce

1. **A scratch report** at `~/.claude/telemetry/mining-runs/<timestamp>.md` listing:
   - Sessions processed (count, total tokens, total wall time)
   - Corrections found (places where user redirected the agent)
   - Patterns found (workflows that succeeded notably)
   - Failure modes found (mistakes that recurred ≥2 times)

2. **Proposed patches** for human review:
   - `~/.claude/telemetry/mining-runs/<timestamp>/lessons.diff` — proposed additions to `lessons.md`
   - `~/.claude/telemetry/mining-runs/<timestamp>/rules-<name>.diff` — proposed additions to specific rules
   - `~/.claude/telemetry/mining-runs/<timestamp>/agent-tuning.md` — agents that should be tuned (recurring failures)

3. **A short summary** to stdout: "5 corrections, 2 patterns, 3 failure modes. Diffs at <path>. Apply with /apply-mining-patches."

## How you do it

### Step 1: Find sessions
```bash
# Sessions live at ~/.claude/projects/<project-dir>/<uuid>.jsonl
SINCE_TS=$(date -d "$since ago" +%s 2>/dev/null || date -v-${since} +%s)
find ~/.claude/projects -name "*.jsonl" -newer <(date -d "@$SINCE_TS") 2>/dev/null
```

Filter:
- Skip files <2KB (test/empty)
- Skip files in `agent-*.jsonl` form (subagent sidechains — extract with their parent, not separately)

### Step 2: Pre-filter for signal
Parsing every event is expensive. Pre-filter for events that contain learning signal:
- `user` messages that come right after an `assistant` message (likely corrections)
- Tool errors (failure modes)
- Long assistant messages right before user "no" / "stop" / "wait" (interruptions)

A 100MB transcript usually compresses to ~5% interesting events.

### Step 3: Mine with Haiku
For each filtered chunk, invoke `claude -p` with `--model claude-haiku-4-5-20251001` and the extraction prompt:

```bash
claude --bare -p "$(cat ~/.claude/skills/mine-transcripts/extract-prompt.md)" \
  --model claude-haiku-4-5-20251001 \
  --output-format json \
  --json-schema "$(cat ~/.claude/skills/mine-transcripts/output.schema.json)" \
  --max-turns 1 \
  < "$chunk"
```

The schema-enforced output gives structured records.

### Step 4: Cluster and dedupe
- Cluster corrections by topic (use Haiku again with a clustering prompt, or simple keyword-based grouping)
- Drop duplicates (same lesson learned twice in two sessions becomes one entry)
- Tag each finding with its source session ID for traceability

### Step 5: Generate diffs
Write proposed additions to `lessons.md` and rules/*.md as **unified diffs** (not direct edits — human reviews first).

Each lesson entry MUST follow the format from `~/.claude/CLAUDE.md` user/feedback memory style:
```markdown
## <date> — <title>

<rule statement>

**Why:** <reason / incident reference>
**How to apply:** <when this kicks in>
**Source:** session=<id>, turn=<n>
```

### Step 6: Surface to user
Print summary, list output paths. Tell the user how to apply: review the diffs, then either `git apply` or copy-paste, or invoke `/apply-mining-patches <run-timestamp>` (a follow-up skill that does the apply for you).

## Cost discipline

A 7-day mining run on a heavy user can cost $0.50–$2.00 with Haiku. Hard limits:
- Max 200 sessions per run
- Max 50K tokens per session (truncate longer)
- Skip sessions already mined (track in `~/.claude/telemetry/mining-runs/.processed.jsonl`)

If projected cost exceeds $5, stop and ask the user.

## When NOT to mine

- During an active fleet (you'll mine your own in-progress session)
- Right after a major CLAUDE.md edit (mining will pick up the edit-related noise)
- When `~/.claude/telemetry/mining-runs/.processed.jsonl` shows the same sessions were mined <24h ago
