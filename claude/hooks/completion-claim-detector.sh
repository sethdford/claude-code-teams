#!/usr/bin/env bash
# UserPromptSubmit hook — detect when the user (or assistant in a sub-turn)
# is making a "task is done" claim, and inject a system reminder to /verify
# before agreeing.
#
# This is a "soft nudge" — does not block, just adds context the model can read.
# Cooldown: don't fire twice within 60s in the same session (avoid nag spam).

set -euo pipefail

input="$(cat)"
prompt="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('prompt') or e.get('user_prompt') or e.get('text') or '')" 2>/dev/null || true)"
sid="$(echo "$input" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('session_id') or '')" 2>/dev/null || true)"

[[ -z "$prompt" ]] && exit 0

# Cooldown check
COOLDOWN_DIR="$HOME/.claude/telemetry/claim-cooldown"
mkdir -p "$COOLDOWN_DIR"
cooldown_file="$COOLDOWN_DIR/${sid:-no-sid}.last"

if [[ -f "$cooldown_file" ]]; then
  last="$(cat "$cooldown_file" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  if (( now - last < 60 )); then
    exit 0  # cooldown active
  fi
fi

# Detect completion-claim phrases (lowered, regex)
lower="$(echo "$prompt" | tr '[:upper:]' '[:lower:]')"
matched=""
for pat in \
  "i think (it'?s |that'?s )?done" \
  "the fix is in" \
  "should be (working|fixed|good) (now|right)" \
  "ready to (commit|merge|ship|push)" \
  "looks (correct|good|right)" \
  "i'?m done with (this|that|the)" \
  "we'?re done with" \
  "all (set|good|fixed)" \
  "task (is |should be )?complete" \
  ; do
  if echo "$lower" | grep -Eq "$pat"; then
    matched="$pat"
    break
  fi
done

[[ -z "$matched" ]] && exit 0

# Mark cooldown
date +%s > "$cooldown_file"

# Print injection — this becomes additionalContext that Claude reads
cat <<'INJECT'
## Reminder: completion claim detected

Before agreeing that the task is done, run `/verify` to spawn the verifier agent. The verifier:
- Runs the actual code (tests, curl, exec) — does not rely on reading
- Captures verbatim output as evidence
- Returns RESULT_verifier=PASS|FAIL|INCONCLUSIVE
- The TaskCompleted hook will check for this evidence; without it, closure is blocked

If this is a trivial task that doesn't need verification, prefix with "trivial:" in the task description (e.g., "trivial: rename variable").
INJECT

# Log the trigger to telemetry for observability
mkdir -p "$HOME/.claude/telemetry"
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"session_id\":\"$sid\",\"matched\":\"$matched\",\"prompt_excerpt\":$(echo "$prompt" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()[:200]))")}" \
  >> "$HOME/.claude/telemetry/claim-detections.jsonl"

exit 0
