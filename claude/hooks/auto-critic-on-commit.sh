#!/usr/bin/env bash
# PreToolUse hook — when about to invoke a `git commit` Bash command, spawn the
# critic agent first to review the staged diff. CRITICAL findings → exit 2 (block);
# HIGH/MED → log + warn but allow.
#
# Matcher (configure in settings.json): "Bash" — and we filter inside the script
# for actual `git commit` invocations.
#
# Cost cap: $0.20 per critic run.
# Time cap: 90s.
#
# Bypass: $CLAUDE_AUTO_CRITIC_BYPASS=1, or commit messages with "[skip-critic]"

set -euo pipefail

if [[ "${CLAUDE_AUTO_CRITIC_BYPASS:-0}" == "1" ]]; then
  exit 0
fi

# Read PreToolUse input
input="$(cat)"
cmd="$(echo "$input" | python3 -c "
import json, sys
e = json.load(sys.stdin)
t = e.get('tool_input') or e.get('tool_use', {}).get('input', {}) or {}
print(t.get('command', ''))
" 2>/dev/null || true)"

# Only act on actual git commit invocations
if ! echo "$cmd" | grep -qE '^[[:space:]]*git[[:space:]]+commit\b'; then
  exit 0
fi

# Bypass on [skip-critic] in commit message
if echo "$cmd" | grep -q '\[skip-critic\]'; then
  echo "[auto-critic] [skip-critic] in commit message — allowing" >&2
  exit 0
fi

# Get the staged diff
cwd="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('cwd') or '')" 2>/dev/null || true)"
[[ -n "$cwd" && -d "$cwd" ]] && cd "$cwd"

# Fall back to wd if not provided
diff="$(git diff --cached 2>/dev/null || true)"
if [[ -z "$diff" ]]; then
  exit 0  # nothing staged, nothing to critic
fi

# Trivial-size bypass: <20 line diffs are usually not worth a critic call
diff_lines="$(echo "$diff" | wc -l | tr -d ' ')"
if (( diff_lines < 20 )); then
  exit 0
fi

mkdir -p "$HOME/.claude/telemetry/auto-critic"
log="$HOME/.claude/telemetry/auto-critic/$(date -u +%Y%m%dT%H%M%SZ).jsonl"
diff_path="${log}.diff"
echo "$diff" > "$diff_path"

echo "[auto-critic] reviewing $diff_lines-line diff..." >&2

prompt="Use the critic agent to review the diff at $diff_path for half-fixes, missing edge cases, and silent failures. The change is about to be committed. Be brutal. Report RESULT_critic=CLEAN | HAS_FINDINGS_<critical>_<high>."

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  flags=("--bare" "-p" "--output-format" "stream-json" "--max-turns" "8" "--max-budget-usd" "0.20" "--verbose" "--allowedTools" "Read,Glob,Grep,Bash,Agent")
else
  flags=("-p" "--output-format" "stream-json" "--max-turns" "8" "--max-budget-usd" "0.20" "--verbose" "--setting-sources" "user" "--exclude-dynamic-system-prompt-sections" "--allowedTools" "Read,Glob,Grep,Bash,Agent" "--no-session-persistence")
fi

if timeout 120 claude "${flags[@]}" <<<"$prompt" > "$log" 2>"${log}.stderr"; then
  result="$(grep -oE 'RESULT_critic=(CLEAN|HAS_FINDINGS_[0-9]+_[0-9]+)' "$log" | tail -1 || true)"

  if [[ "$result" == *CLEAN ]]; then
    echo "[auto-critic] CLEAN — proceeding with commit" >&2
    exit 0
  fi

  # Parse counts
  if [[ "$result" =~ HAS_FINDINGS_([0-9]+)_([0-9]+) ]]; then
    n_crit="${BASH_REMATCH[1]}"
    n_high="${BASH_REMATCH[2]}"
    if (( n_crit > 0 )); then
      cat >&2 <<EOF
[auto-critic] BLOCKED — $n_crit CRITICAL finding(s) in this commit.

Review at $log
Diff at $diff_path

To override: add [skip-critic] to commit message, or set CLAUDE_AUTO_CRITIC_BYPASS=1.
EOF
      exit 2
    elif (( n_high > 0 )); then
      echo "[auto-critic] WARN — $n_high HIGH finding(s) but no CRITICAL. Proceeding. Review: $log" >&2
      exit 0
    fi
  fi

  echo "[auto-critic] no clear result line; allowing commit. Log: $log" >&2
  exit 0
else
  echo "[auto-critic] critic subprocess failed/timeout. Allowing commit. Log: ${log}.stderr" >&2
  exit 0
fi
