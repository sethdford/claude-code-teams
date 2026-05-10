#!/usr/bin/env bash
# TaskCompleted hook — if no RESULT_verifier=PASS evidence in session,
# AUTOMATICALLY spawn the verifier headlessly to produce one.
#
# Difference vs verify-gate.sh:
#   verify-gate    blocks (exit 2) and asks user to /verify
#   auto-verify    spawns verifier itself, captures evidence, passes through
#
# Both are wired: verify-gate runs FIRST (cheap check). If it would block,
# auto-verify steps in to attempt the verification rather than failing.
#
# Bypasses (unchanged):
#   - $CLAUDE_VERIFY_GATE_BYPASS=1
#   - Trivial tasks (trivial: prefix, doc only, comment only, format only, rename)
#   - First call in fresh session
#   - Already has RESULT_verifier=PASS evidence
#
# Cost cap: $0.10 per auto-verify (--max-budget-usd 0.10).
# Time cap: 60s (subprocess timeout).

set -euo pipefail

if [[ "${CLAUDE_VERIFY_GATE_BYPASS:-0}" == "1" ]]; then
  exit 0
fi

# Read input
input="$(cat)"
sid="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('session_id') or '')" 2>/dev/null || true)"
task_text="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); t=e.get('task'); print(t.get('content','') if isinstance(t, dict) else '')" 2>/dev/null || true)"

# Trivial bypass
lower="$(echo "$task_text" | tr '[:upper:]' '[:lower:]')"
case "$lower" in
  *trivial:*|*"doc only"*|*"comment only"*|*"format only"*|*"rename "*) exit 0 ;;
esac

# No session_id → can't audit, allow
if [[ -z "$sid" ]]; then exit 0; fi

# Find session JSONL
jsonl="$(find "$HOME/.claude/projects" -name "${sid}.jsonl" -type f 2>/dev/null | head -1)"
if [[ -z "$jsonl" || ! -f "$jsonl" ]]; then exit 0; fi

# Already PASS? Pass through.
recent="$(tail -n 300 "$jsonl" | grep -oE 'RESULT_verifier=(PASS|FAIL|INCONCLUSIVE)' | tail -1 || true)"
if [[ "$recent" == *PASS ]]; then exit 0; fi

# If recent FAIL/INCONCLUSIVE, surface it (don't auto-retry — user should know)
if [[ -n "$recent" ]]; then
  echo "[auto-verify] last verifier result: $recent — not auto-retrying. Run /verify after fixing." >&2
  exit 2
fi

# No evidence at all. Auto-spawn the verifier headlessly.
echo "[auto-verify] no RESULT_verifier= evidence yet. Spawning verifier headlessly..." >&2

mkdir -p "$HOME/.claude/telemetry/auto-verify"
log="$HOME/.claude/telemetry/auto-verify/$(date -u +%Y%m%dT%H%M%SZ).jsonl"

# Compose a verification prompt from the task description
verify_prompt="Use the verifier agent to verify the recent change related to this task: '$task_text'. Run any tests, capture evidence, report RESULT_verifier=PASS|FAIL|INCONCLUSIVE."

# Pick auth strategy
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  flags=("--bare" "-p" "--output-format" "stream-json" "--include-partial-messages" "--max-turns" "10" "--max-budget-usd" "0.10" "--verbose" "--allowedTools" "Read,Glob,Grep,Bash,Agent")
else
  flags=("-p" "--output-format" "stream-json" "--include-partial-messages" "--max-turns" "10" "--max-budget-usd" "0.10" "--verbose" "--setting-sources" "user" "--exclude-dynamic-system-prompt-sections" "--allowedTools" "Read,Glob,Grep,Bash,Agent" "--no-session-persistence")
fi

# Run with timeout. Capture output.
if timeout 90 claude "${flags[@]}" <<<"$verify_prompt" > "$log" 2>"${log}.stderr"; then
  result="$(grep -oE 'RESULT_verifier=(PASS|FAIL|INCONCLUSIVE)' "$log" | tail -1 || true)"
  if [[ "$result" == *PASS ]]; then
    echo "[auto-verify] $result — passing through" >&2
    exit 0
  elif [[ -n "$result" ]]; then
    echo "[auto-verify] $result — task closure blocked. See $log" >&2
    exit 2
  else
    echo "[auto-verify] verifier produced no RESULT_ line. Allowing closure but flagging." >&2
    exit 0
  fi
else
  echo "[auto-verify] verifier subprocess failed/timeout. See $log.stderr. Allowing closure." >&2
  exit 0
fi
