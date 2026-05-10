#!/usr/bin/env bash
# PostToolUse hook — when an Edit/Write touches ~/.claude/agents/*.md or
# ~/.claude/skills/*/SKILL.md, queue an /eval run for that target.
#
# Debounced: queues with a 5-minute settle timer. If the file is edited again
# within 5 min, the timer resets. Eval runs only after 5 min of stability.
#
# This prevents thrashing while you iterate; you only eval when you're done editing.

set -euo pipefail

input="$(cat)"

# Extract edited file path from PostToolUse event
file="$(echo "$input" | python3 -c "
import json, sys
e = json.load(sys.stdin)
t = e.get('tool_input') or e.get('tool_use', {}).get('input', {}) or {}
print(t.get('file_path') or t.get('path') or '')
" 2>/dev/null || true)"

[[ -z "$file" ]] && exit 0

# Match either ~/.claude/agents/<name>.md or ~/.claude/skills/<name>/SKILL.md
target=""
if [[ "$file" =~ \.claude/agents/([^/]+)\.md$ ]]; then
  target="${BASH_REMATCH[1]}"
elif [[ "$file" =~ \.claude/skills/([^/]+)/SKILL\.md$ ]]; then
  target="${BASH_REMATCH[1]}"
fi

[[ -z "$target" ]] && exit 0

# Debounce queue
QUEUE_DIR="$HOME/.claude/telemetry/eval-queue"
mkdir -p "$QUEUE_DIR"
queue_file="$QUEUE_DIR/${target}.queued"
echo "$(date +%s) $file" > "$queue_file"

# Spawn the debounce-and-fire daemon (only one per target at a time)
# Uses a lockfile to ensure only one waiter exists per target.
LOCK_DIR="$HOME/.claude/telemetry/eval-locks"
mkdir -p "$LOCK_DIR"
lock="$LOCK_DIR/${target}.lock"

if [[ -f "$lock" ]]; then
  # An existing waiter will pick up the updated queue file
  exit 0
fi

# Spawn waiter in background. It will:
# 1. Sleep 5 min
# 2. Check the queue file's mtime — if newer than its start, it's been retriggered → exit
# 3. Otherwise run /eval
(
  echo $$ > "$lock"
  start=$(date +%s)
  sleep 300

  # Has the queue been retriggered since we started?
  if [[ -f "$queue_file" ]]; then
    queue_ts="$(stat -f %m "$queue_file" 2>/dev/null || stat -c %Y "$queue_file" 2>/dev/null || echo 0)"
    if (( queue_ts > start )); then
      # Re-triggered — let the next waiter handle it
      rm -f "$lock"
      exit 0
    fi
  fi

  # Run the eval
  echo "[auto-eval] target=$target firing after 5min settle" >&2
  if [[ -d "$HOME/.claude/evals/scenarios/$target" ]]; then
    "$HOME/.claude/evals/_runner/run.sh" "$target" \
      > "$HOME/.claude/telemetry/auto-eval-${target}-$(date -u +%Y%m%dT%H%M%SZ).log" 2>&1 \
      || echo "[auto-eval] $target eval failed" >&2
  else
    echo "[auto-eval] no scenarios for $target — skipping" >&2
  fi

  rm -f "$lock" "$queue_file"
) &

disown
exit 0
