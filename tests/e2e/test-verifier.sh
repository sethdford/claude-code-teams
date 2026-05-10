#!/usr/bin/env bash
# tests/e2e/test-verifier.sh — REAL end-to-end test against the verifier agent.
#
# Invokes `claude -p` headlessly, asks the verifier agent to verify a known-good
# Python module, and asserts the output contains RESULT_verifier=PASS.
#
# Requires: Claude Code 2.1.32+ AND either ANTHROPIC_API_KEY env var or
# subscription auth (the script auto-detects which).
#
# Cost: ~$0.05-0.20 per run.
# Wall time: ~30-60s.
#
# Usage:
#   ./tests/e2e/test-verifier.sh
#   ./tests/e2e/test-verifier.sh --debug   # keep run dir for inspection

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURES="$REPO_DIR/tests/fixtures"
RUN_DIR="$REPO_DIR/tests/e2e/runs/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"

DEBUG=0
[[ "${1:-}" == "--debug" ]] && DEBUG=1

# Verify prerequisites
command -v claude >/dev/null || { echo "claude CLI not found in PATH"; exit 1; }
command -v python3 >/dev/null || { echo "python3 required"; exit 1; }

echo "=== E2E: verifier agent on a known-good module ==="
echo "Run dir: $RUN_DIR"
echo ""

# Copy fixtures into a temp working dir so verifier can run them
WORK_DIR="$RUN_DIR/work"
mkdir -p "$WORK_DIR"
cp "$FIXTURES/eval_target_pass.py" "$WORK_DIR/"
cp "$FIXTURES/test_eval_target_pass.py" "$WORK_DIR/"

# Confirm the target tests pass when run directly (sanity check our fixture)
echo "Sanity check — fixture tests should pass standalone:"
(cd "$WORK_DIR" && python3 test_eval_target_pass.py 2>&1) | tail -5
echo ""

# Build the prompt
PROMPT="cd $WORK_DIR. Use the verifier agent to verify the function add(a, b) in eval_target_pass.py works correctly. Contract:
1. Returns sum of two integers
2. Rejects None inputs by raising TypeError

Run the tests at test_eval_target_pass.py. Report findings with RESULT_verifier=PASS|FAIL|INCONCLUSIVE on the last line."

# Pick auth strategy
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  AUTH="bare"
  FLAGS=("--bare" "-p" "--output-format" "stream-json" "--include-partial-messages" "--verbose" "--max-turns" "10" "--max-budget-usd" "0.30" "--allowedTools" "Read,Glob,Grep,Bash,Agent")
else
  AUTH="user-settings"
  FLAGS=("-p" "--output-format" "stream-json" "--include-partial-messages" "--verbose" "--max-turns" "10" "--max-budget-usd" "0.30" "--allowedTools" "Read,Glob,Grep,Bash,Agent" "--no-session-persistence" "--setting-sources" "user" "--exclude-dynamic-system-prompt-sections")
fi
echo "Auth mode: $AUTH"
echo ""

JSONL="$RUN_DIR/output.jsonl"
ERR="$RUN_DIR/output.stderr"

echo "Running: claude ${FLAGS[*]}"
echo ""
start=$(date +%s)
# macOS doesn't ship `timeout`; --max-turns + --max-budget-usd already bound the run.
# If gtimeout/timeout is available, prepend it; otherwise run without.
if command -v gtimeout >/dev/null 2>&1; then
  CMD_PREFIX="gtimeout 180"
elif command -v timeout >/dev/null 2>&1; then
  CMD_PREFIX="timeout 180"
else
  CMD_PREFIX=""
fi

echo "$PROMPT" | $CMD_PREFIX claude "${FLAGS[@]}" > "$JSONL" 2>"$ERR" || claude_rc=$?
claude_rc="${claude_rc:-0}"
end=$(date +%s)
echo "Wall time: $((end - start))s"
echo ""

# Detect API errors first (rate limit, auth, server) — these are ENVIRONMENT issues,
# not system failures. Surface them clearly.
API_ERR="$(python3 - "$JSONL" <<'PY'
import json, sys
path = sys.argv[1]
try:
    last_result = None
    for line in open(path):
        try: e = json.loads(line)
        except json.JSONDecodeError: continue
        if e.get("type") == "result":
            last_result = e
    if last_result and last_result.get("is_error"):
        st = last_result.get("api_error_status")
        msg = last_result.get("result", "")
        print(f"{st}|{msg[:200]}")
except FileNotFoundError:
    pass
PY
)"
if [[ -n "$API_ERR" ]]; then
  status="${API_ERR%%|*}"
  msg="${API_ERR##*|}"
  echo ""
  echo "=== Environment error (NOT a system failure) ==="
  echo "API status: $status"
  echo "Message: $msg"
  echo ""
  case "$status" in
    429) echo "RATE_LIMITED — your Claude subscription is exhausted. The harness invoked claude correctly, but the API returned 429."
         echo "This is environment, not us. Re-run after quota resets, or set ANTHROPIC_API_KEY for --bare mode."
         exit 2 ;;
    401|403) echo "AUTHENTICATION_FAILED — credentials missing or invalid. Run 'claude /login' or set ANTHROPIC_API_KEY."
             exit 2 ;;
    5*) echo "SERVER_ERROR — API returned $status. Retry."
        exit 2 ;;
    *) echo "API_ERROR — non-success status. See $JSONL."
       exit 2 ;;
  esac
fi

# No API error — extract RESULT_verifier= from the assistant text content
RESULT="$(python3 - "$JSONL" <<'PY'
import json, re, sys
path = sys.argv[1]
text = ""
with open(path) as f:
    for line in f:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "assistant":
            for b in (evt.get("message") or {}).get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "text":
                    text += b.get("text", "") + "\n"
m = re.findall(r"RESULT_verifier=(PASS|FAIL|INCONCLUSIVE)", text)
print(m[-1] if m else "MISSING")
PY
)"

# Extract cost + token usage
USAGE="$(python3 - "$JSONL" <<'PY'
import json, sys
path = sys.argv[1]
final = None
with open(path) as f:
    for line in f:
        try: evt = json.loads(line)
        except json.JSONDecodeError: continue
        if evt.get("type") == "result":
            final = evt
print(json.dumps({
    "cost_usd": (final or {}).get("total_cost_usd", 0),
    "duration_ms": (final or {}).get("duration_ms", 0),
    "num_turns": (final or {}).get("num_turns", 0),
    "usage": (final or {}).get("usage", {}),
}, indent=2))
PY
)"

echo "=== Result ==="
echo "RESULT_verifier=$RESULT"
echo ""
echo "Usage:"
echo "$USAGE"
echo ""

if [[ "$RESULT" == "PASS" ]]; then
  echo "✅ E2E PASS"
  rc=0
elif [[ "$RESULT" == "FAIL" ]]; then
  echo "❌ Verifier reported FAIL — check $JSONL"
  rc=1
elif [[ "$RESULT" == "INCONCLUSIVE" ]]; then
  echo "⚠ Verifier reported INCONCLUSIVE — check $JSONL"
  rc=1
else
  echo "✗ Verifier did not emit RESULT_verifier= line"
  echo "  This may mean: agent not loaded, or agent didn't follow output contract."
  echo "  Inspect: $JSONL"
  rc=1
fi

if [[ $DEBUG -eq 0 ]]; then
  rm -rf "$RUN_DIR/work"
fi

echo ""
echo "Full transcript: $JSONL"
exit $rc
