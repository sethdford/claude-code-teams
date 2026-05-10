#!/usr/bin/env bash
# TaskCompleted gate — checks for RESULT_verifier=PASS evidence in recent
# session output. If not found, exits 2 to block task closure with a hint.
#
# Reads JSON event from stdin (session_id, task info). Looks up the active
# session JSONL and greps the last 200 events for RESULT_verifier=.
#
# Bypasses (allow closure even without verifier):
#   - Trivial tasks (input contains "trivial:" or task name has "doc"/"comment")
#   - $CLAUDE_VERIFY_GATE_BYPASS=1 set in env
#   - First call in a fresh session (no JSONL yet)

set -euo pipefail

if [[ "${CLAUDE_VERIFY_GATE_BYPASS:-0}" == "1" ]]; then
  echo "[verify-gate] bypassed via env var"
  exit 0
fi

# Read input event
input="$(cat)"
sid="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('session_id') or '')" 2>/dev/null || true)"
task_text="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('task',{}).get('content','') if isinstance(e.get('task'), dict) else '')" 2>/dev/null || true)"

# Trivial-task bypass
lower_task="$(echo "$task_text" | tr '[:upper:]' '[:lower:]')"
case "$lower_task" in
  *trivial:*|*"doc only"*|*"comment only"*|*"format only"*|*"rename "*)
    echo "[verify-gate] trivial task; bypassing"
    exit 0
    ;;
esac

if [[ -z "$sid" ]]; then
  echo "[verify-gate] no session_id; allowing (cannot verify)"
  exit 0
fi

# Find the session JSONL — search across all projects
jsonl="$(find ~/.claude/projects -name "${sid}.jsonl" -type f 2>/dev/null | head -1)"

if [[ -z "$jsonl" || ! -f "$jsonl" ]]; then
  echo "[verify-gate] no session transcript yet; allowing"
  exit 0
fi

# Look at last 300 lines for verifier evidence
recent_result="$(tail -n 300 "$jsonl" | grep -oE 'RESULT_verifier=(PASS|FAIL|INCONCLUSIVE)' | tail -1 || true)"

if [[ -z "$recent_result" ]]; then
  cat >&2 <<EOF
[verify-gate] BLOCKED — no recent RESULT_verifier= evidence in this session.

Before marking this task complete, run /verify on the change:
  - It spawns the verifier agent which runs the code and captures evidence
  - Verifier emits RESULT_verifier=PASS|FAIL|INCONCLUSIVE
  - This gate looks for that line and only allows closure on PASS

To bypass for trivial tasks, name them with "trivial:" prefix or set CLAUDE_VERIFY_GATE_BYPASS=1.
EOF
  exit 2
fi

case "$recent_result" in
  *PASS) echo "[verify-gate] $recent_result — allowing"; exit 0 ;;
  *) cat >&2 <<EOF
[verify-gate] BLOCKED — last verifier result was: $recent_result

Re-run /verify after fixing, or accept that the task is not done.
EOF
     exit 2 ;;
esac
