#!/usr/bin/env bash
# eval runner — invokes claude -p headless against scenarios, captures stream-json events
#
# Usage: run.sh <target>
#   target = skill name, agent name, rule filename, or "all"
#
# Output: ~/.claude/evals/runs/<target>/<ISO-timestamp>/
#   ├── scenario-<n>.jsonl     # raw stream-json events
#   ├── scenario-<n>.summary   # programmatic detection summary
#   └── manifest.json          # run metadata
#
# Auth modes:
#   - If $ANTHROPIC_API_KEY is set: uses --bare (clean isolated context)
#   - Otherwise: uses --setting-sources user --exclude-dynamic-system-prompt-sections
#     (loads global ~/.claude but skips project pollution; uses subscription auth)

set -euo pipefail

TARGET="${1:?target required}"
EVAL_ROOT="$HOME/.claude/evals"
SCENARIOS_DIR="$EVAL_ROOT/scenarios/$TARGET"
RUNS_DIR="$EVAL_ROOT/runs/$TARGET"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUNS_DIR/$TIMESTAMP"
MAX_BUDGET="${EVAL_MAX_BUDGET_USD:-2}"

if [[ "$TARGET" == "all" ]]; then
  echo "[eval] Running all targets..."
  for t in "$EVAL_ROOT/scenarios"/*/; do
    [[ -d "$t" ]] || continue
    name="$(basename "$t")"
    [[ "$name" == "_runner" ]] && continue
    "$0" "$name" || echo "[eval] $name FAILED"
  done
  exit 0
fi

if [[ ! -d "$SCENARIOS_DIR" ]]; then
  echo "[eval] no scenarios for target: $TARGET" >&2
  echo "[eval] author scenarios at: $SCENARIOS_DIR (see scenarios/README.md)" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

# Pick invocation strategy based on available auth
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  AUTH_MODE="bare"
  CLAUDE_FLAGS=(
    "--bare"
    "-p"
    "--output-format" "stream-json"
    "--include-partial-messages"
    "--include-hook-events"
    "--verbose"
    "--max-turns" "5"
    "--max-budget-usd" "$MAX_BUDGET"
    "--allowedTools" "Read,Glob,Grep,Bash,Edit,Write,Agent,Skill,Task"
  )
else
  # Subscription auth: use full claude -p but limit settings sources to user only
  AUTH_MODE="user-settings"
  CLAUDE_FLAGS=(
    "-p"
    "--output-format" "stream-json"
    "--include-partial-messages"
    "--include-hook-events"
    "--verbose"
    "--max-turns" "5"
    "--max-budget-usd" "$MAX_BUDGET"
    "--setting-sources" "user"
    "--exclude-dynamic-system-prompt-sections"
    "--allowedTools" "Read,Glob,Grep,Bash,Edit,Write,Agent,Skill,Task"
    "--no-session-persistence"
  )
fi

echo "[eval] target=$TARGET timestamp=$TIMESTAMP auth=$AUTH_MODE"
echo "[eval] run_dir=$RUN_DIR"

# Manifest
cat > "$RUN_DIR/manifest.json" <<EOF
{
  "target": "$TARGET",
  "timestamp": "$TIMESTAMP",
  "host": "$(hostname)",
  "claude_version": "$(claude --version 2>/dev/null | tr -d '\n' || echo unknown)",
  "auth_mode": "$AUTH_MODE",
  "max_budget_usd": $MAX_BUDGET,
  "scenarios": []
}
EOF

scenario_count=0
for scenario_file in "$SCENARIOS_DIR"/*.md; do
  [[ -f "$scenario_file" ]] || continue
  [[ "$(basename "$scenario_file")" == "README.md" ]] && continue
  scenario_count=$((scenario_count + 1))
  name="$(basename "$scenario_file" .md)"
  echo "[eval] scenario: $name"

  # Extract prompt from frontmatter via python (cleaner than awk for quoted values)
  prompt="$(python3 - "$scenario_file" <<'PYEXTRACT'
import re, sys
text = open(sys.argv[1]).read()
m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
if not m:
    sys.exit(1)
fm = m.group(1)
mp = re.search(r"^prompt:\s*(.+)$", fm, flags=re.M)
if mp:
    val = mp.group(1).strip()
    # strip quotes if present
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    print(val)
PYEXTRACT
  )"

  if [[ -z "$prompt" ]]; then
    echo "[eval]   no 'prompt:' in frontmatter; skipping"
    continue
  fi

  jsonl="$RUN_DIR/scenario-${name}.jsonl"
  summary="$RUN_DIR/scenario-${name}.summary"

  start=$(date +%s)
  echo "$prompt" | claude "${CLAUDE_FLAGS[@]}" \
    > "$jsonl" 2> "$RUN_DIR/scenario-${name}.stderr" || {
      echo "[eval]   ERROR (claude exit non-zero, see stderr)"
    }
  end=$(date +%s)
  duration=$((end - start))

  # Programmatic detection
  python3 "$EVAL_ROOT/_runner/detect.py" "$jsonl" "$scenario_file" "$duration" > "$summary" 2>&1 || true

  # One-line summary line for the runner output
  trigger=$(grep -E '^trigger=' "$summary" | head -1)
  cache=$(grep -E '^cache_hit_rate=' "$summary" | head -1)
  cost=$(grep -E '^cost_usd=' "$summary" | head -1)
  echo "[eval]   $trigger $cache $cost (${duration}s)"
done

# Update manifest with scenario count
python3 -c "
import json
with open('$RUN_DIR/manifest.json') as f: m = json.load(f)
m['scenario_count'] = $scenario_count
with open('$RUN_DIR/manifest.json', 'w') as f: json.dump(m, f, indent=2)
"

echo "[eval] done. $scenario_count scenarios. results in $RUN_DIR"
