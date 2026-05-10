#!/usr/bin/env bash
# PreToolUse hook — gate destructive/irreversible operations through a fast
# constitutional check before they execute.
#
# Pattern: OpenAI's Deliberate Alignment (Dec 2024) — chain-of-thought reasoning
# over a written spec robustifies refusals. We do the prompt-only version: when
# a Bash command matches a "destructive" pattern, spawn a fast Haiku critic that
# answers ONE question: "is this action consistent with the user's stated goal
# and the constitution at ~/.claude/constitution.md?". Answer NO → exit 2 (block).
#
# Bypasses:
#   - $CLAUDE_CONSTITUTIONAL_GATE_BYPASS=1
#   - Pattern in commit message: [skip-constitutional]
#   - Trivial: rename, format, comment-only diffs
#
# Cost: ~$0.005 per gated call (Haiku, 1 turn, ~500 tokens)
# Latency: ~1.5s (acceptable for irreversible ops; would be too slow for routine commands)

set -euo pipefail

if [[ "${CLAUDE_CONSTITUTIONAL_GATE_BYPASS:-0}" == "1" ]]; then
  exit 0
fi

input="$(cat)"
cmd="$(echo "$input" | python3 -c "
import json, sys
e = json.load(sys.stdin)
t = e.get('tool_input') or e.get('tool_use', {}).get('input', {}) or {}
print(t.get('command', ''))
" 2>/dev/null || true)"

[[ -z "$cmd" ]] && exit 0

# Destructive-pattern detection. Only gate the genuinely irreversible.
# Tuned to favor false negatives — we don't want to gate every command.
destructive=0
for pat in \
  'rm[[:space:]]+-rf?[[:space:]]' \
  'git[[:space:]]+push[[:space:]]+--force' \
  'git[[:space:]]+push[[:space:]]+-f([[:space:]]|$)' \
  'git[[:space:]]+reset[[:space:]]+--hard' \
  'git[[:space:]]+branch[[:space:]]+-D' \
  'DROP[[:space:]]+TABLE' \
  'DROP[[:space:]]+DATABASE' \
  'TRUNCATE[[:space:]]+TABLE' \
  'DELETE[[:space:]]+FROM' \
  'aws[[:space:]]+s3[[:space:]]+rm[[:space:]]+--recursive' \
  'gcloud[[:space:]]+.*[[:space:]]+delete' \
  'kubectl[[:space:]]+delete' \
  'helm[[:space:]]+uninstall' \
  'pkill[[:space:]]+-9' \
  'shutdown[[:space:]]' \
  'reboot([[:space:]]|$)' \
  ; do
  if echo "$cmd" | grep -qE "$pat"; then
    destructive=1
    break
  fi
done

[[ "$destructive" -eq 0 ]] && exit 0

# Bypass via [skip-constitutional] in command (e.g., embedded in commit message)
if echo "$cmd" | grep -q '\[skip-constitutional\]'; then
  echo "[constitutional] [skip-constitutional] — allowing" >&2
  exit 0
fi

# Read constitution (or use default if missing)
CONSTITUTION="$HOME/.claude/constitution.md"
if [[ ! -f "$CONSTITUTION" ]]; then
  cat > "$CONSTITUTION" <<'CONST'
# Operating Constitution

The agent must NOT execute destructive operations unless ALL of these hold:
1. The action is consistent with what the user just asked for (not an extrapolation).
2. The blast radius is bounded: only files/resources the user owns or has explicit authority over.
3. There exists a recovery path: backup, snapshot, undo command, or unaffected replica.
4. If the action could affect another person, that person has been notified.
5. If the action could affect production systems, there is a rollback plan documented.

The agent must REFUSE to execute when:
- The action would push to a branch shared with others without their review (force-push to main)
- The action drops a production database, table, or namespace without an explicit confirmation in the prompt
- The action deletes user data without an explicit confirmation
- The action terminates a process owned by another user
- The action modifies system files (/etc, /System, /Library) without sudo + explicit user request
CONST
  echo "[constitutional] created default $CONSTITUTION" >&2
fi

# Get user's stated goal — extract from the most recent user message in the session
sid="$(echo "$input" | python3 -c "
import json,sys; e=json.load(sys.stdin); print(e.get('session_id') or '')
" 2>/dev/null || true)"

user_goal="<unknown>"
if [[ -n "$sid" ]]; then
  jsonl="$(find $HOME/.claude/projects -name "${sid}.jsonl" -type f 2>/dev/null | head -1)"
  if [[ -n "$jsonl" && -f "$jsonl" ]]; then
    user_goal="$(python3 - "$jsonl" <<'PY'
import json, sys
last_user = ""
for line in open(sys.argv[1]):
    try: e = json.loads(line)
    except json.JSONDecodeError: continue
    if e.get("type") == "user":
        msg = e.get("message", {}).get("content", "")
        if isinstance(msg, list):
            for b in msg:
                if isinstance(b, dict) and b.get("type") == "text":
                    last_user = b.get("text", "")
        else:
            last_user = str(msg)
print(last_user[:500])
PY
)"
  fi
fi

# Spawn the fast critic via claude -p (Haiku, 1 turn, low budget)
mkdir -p "$HOME/.claude/telemetry/constitutional"
log="$HOME/.claude/telemetry/constitutional/$(date -u +%Y%m%dT%H%M%SZ).jsonl"

prompt="You are a constitutional reviewer. Read the constitution and the about-to-execute command. Answer YES or NO with one short reason.

CONSTITUTION:
$(cat "$CONSTITUTION")

USER'S STATED GOAL (most recent prompt):
$user_goal

ABOUT-TO-EXECUTE COMMAND:
$cmd

Is this command consistent with the user's stated goal AND the constitution? Respond on a single line:
DECISION: YES | NO
REASON: <one short sentence>"

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  flags=("--bare" "-p" "--max-turns" "1" "--max-budget-usd" "0.02" "--model" "claude-haiku-4-5-20251001" "--output-format" "json")
else
  flags=("-p" "--max-turns" "1" "--max-budget-usd" "0.02" "--model" "claude-haiku-4-5-20251001" "--output-format" "json" "--setting-sources" "user" "--exclude-dynamic-system-prompt-sections" "--no-session-persistence")
fi

# Record what we're gating
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"command\":$(echo "$cmd" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:500]))'),\"goal\":$(echo "$user_goal" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:500]))')}" >> "$log"

# Run the critic with a hard 30s timeout (we'd rather fail-open than block forever)
critic_out="$(echo "$prompt" | (
  if command -v gtimeout >/dev/null; then gtimeout 30 claude "${flags[@]}";
  elif command -v timeout >/dev/null; then timeout 30 claude "${flags[@]}";
  else claude "${flags[@]}"; fi
) 2>>"${log}.stderr")"

# Parse: extract "DECISION: YES|NO"
decision="$(echo "$critic_out" | python3 -c "
import json, re, sys
text = sys.stdin.read().strip()
try:
    j = json.loads(text)
    text = j.get('result', text) if isinstance(j, dict) else text
except json.JSONDecodeError:
    pass
m = re.search(r'DECISION:\s*(YES|NO)', text, re.IGNORECASE)
print(m.group(1).upper() if m else 'INDETERMINATE')
" 2>/dev/null || echo "INDETERMINATE")"

reason="$(echo "$critic_out" | python3 -c "
import json, re, sys
text = sys.stdin.read().strip()
try:
    j = json.loads(text)
    text = j.get('result', text) if isinstance(j, dict) else text
except json.JSONDecodeError:
    pass
m = re.search(r'REASON:\s*(.+?)(?:\n|$)', text)
print(m.group(1).strip() if m else '(no reason)')
" 2>/dev/null || echo "(parse error)")"

# Log decision
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"decision\":\"$decision\",\"reason\":$(echo "$reason" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:300]))')}" >> "$log"

case "$decision" in
  YES)
    echo "[constitutional] ALLOWED — $reason" >&2
    exit 0
    ;;
  NO)
    cat >&2 <<EOF
[constitutional] BLOCKED

Command: $cmd
Reason:  $reason
Log:     $log

To override: prefix command with [skip-constitutional], or set
CLAUDE_CONSTITUTIONAL_GATE_BYPASS=1 in env. Edit ~/.claude/constitution.md to
adjust the rules.
EOF
    exit 2
    ;;
  *)
    # Critic was indeterminate (timeout, parse error, no API). Fail-OPEN with warning.
    echo "[constitutional] INDETERMINATE — allowing (critic unavailable; review log: $log)" >&2
    exit 0
    ;;
esac
