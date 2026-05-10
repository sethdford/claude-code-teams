---
name: apply-mining-patches
description: Apply the diff/patch outputs from a /mine-transcripts run to lessons.md and rules/*.md after human review. Use after running /mine-transcripts and reviewing the proposed diffs. Triggers on /apply-mining-patches, "apply the mining patches", "apply mining run", "approve and apply the trajectory diffs".
when_to_use: After /mine-transcripts produces diffs and you've reviewed them. Skips approved-then-undone work.
allowed-tools: Bash, Read, Write, Edit
arguments: [run-timestamp]
---

# /apply-mining-patches — Apply approved trajectory-mining diffs

`/apply-mining-patches <run-ts>` applies the lessons + rules diffs from `~/.claude/telemetry/mining-runs/<run-ts>/` to live files, after the user has had a chance to review.

## What you do

### 1. Resolve the run
- If `<run-ts>` is "latest", glob `~/.claude/telemetry/mining-runs/2*` and pick the most recent
- Otherwise use the exact timestamp directory

### 2. Surface what's there
Read and summarize:
- `manifest.json` — sessions mined, signal counts
- `lessons.diff` — proposed additions to `~/.claude/lessons.md`
- `agent-tuning.md` — agents with ≥2 occurrences worth tuning
- Any `rules-<name>.diff` files

### 3. Confirm with user
Present a summary like:
```
Mining run 20260510T120000Z:
  - 12 sessions, 7 corrections, 3 patterns, 4 failure modes
  - lessons.diff: +45 lines (3 new lesson entries)
  - agent-tuning.md: 1 agent recommended (flake-detector, 4 occurrences)
  - rules-self-improvement.diff: +8 lines

Apply? (yes/no/preview)
```

If preview, show the actual diff content (truncated). If no, exit.

### 4. Apply diffs

For lessons.diff: append to `~/.claude/lessons.md`.

```bash
cat <(echo) <(cat <run-dir>/lessons.diff) >> ~/.claude/lessons.md
```

For rule diffs: append to the named rule file.

For agent tuning candidates: do NOT apply automatically. Surface the `/tune-agent <name>` command and let the user run it explicitly. Reflexion patches require their own approval.

### 5. Mark applied

After successful application, write to `<run-dir>/applied.marker` with the apply timestamp. This prevents accidental double-application.

### 6. Commit (if in a git repo)

If the user wants, commit the lessons/rules updates with a message like:
```
docs(memory): apply mining run 20260510T120000Z

3 new lessons, 1 rule update from 12 sessions of trajectory mining.
Refs: ~/.claude/telemetry/mining-runs/20260510T120000Z/
```

## Anti-patterns

- Applying without showing the user the actual content first — patches can be wrong
- Auto-applying agent-tuning candidates — those need /tune-agent's own approval flow
- Applying a run that's already marked applied — fail loudly
- Discarding a run's directory after apply — keep it for reproducibility
- Editing the original miner output file — the diffs are immutable; if a diff is wrong, that's a bug in the miner, fix the miner
