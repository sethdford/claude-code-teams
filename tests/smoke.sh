#!/usr/bin/env bash
# tests/smoke.sh — synthetic smoke test for claude-code-teams.
#
# Validates: file presence, executability, JSON validity, Python imports,
# real-schema parsing for hooks (statusline + log-cache-stats), RL pipeline
# end-to-end, and verify-gate behavior.
#
# Designed to run in CI without real Claude API calls. All claude -p invocations
# are gated behind tests/e2e/.
#
# Usage:
#   ./tests/smoke.sh            # against ~/.claude/ (post-install)
#   CLAUDE_DIR=./claude ./tests/smoke.sh   # against the repo's claude/ dir directly

set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
PASS=0; FAIL=0; T=()

assert() { if eval "$2"; then PASS=$((PASS+1)); T+=("✓ $1"); else FAIL=$((FAIL+1)); T+=("✗ $1"); fi; }

echo "=== claude-code-teams smoke test ==="
echo "CLAUDE_DIR=$CLAUDE_DIR"
echo ""

# 1. File presence
echo "--- file presence ---"
for f in \
  CLAUDE.md \
  skills/eval/SKILL.md skills/verify/SKILL.md skills/cache-report/SKILL.md \
  skills/mine-transcripts/SKILL.md skills/team/SKILL.md skills/spec/SKILL.md \
  skills/tune-agent/SKILL.md skills/best-of-n/SKILL.md skills/ab-test/SKILL.md \
  skills/rl-status/SKILL.md skills/eval-author/SKILL.md skills/aspect-panel/SKILL.md \
  skills/apply-mining-patches/SKILL.md \
  agents/verifier.md agents/critic.md agents/agent-tuner.md agents/spec-verifier.md \
  agents/security-reviewer.md agents/migration-planner.md agents/regression-hunter.md \
  hooks/auto-verify-on-complete.sh hooks/completion-claim-detector.sh \
  hooks/auto-critic-on-commit.sh hooks/auto-eval-on-agent-edit.sh \
  hooks/log-cache-stats.sh hooks/_log_cache_stats.py hooks/verify-gate.sh \
  hooks/session-start-knowledge.sh \
  rl/emit_task_reward.py rl/emit_correction_signal.py rl/emit_session_rewards.py \
  rl/best_of_n.py rl/ab_test.py rl/usc.py rl/aspect_panel.py rl/README.md \
  evals/_runner/run.sh evals/_runner/detect.py evals/_runner/judge.md \
  statusline/statusline.py \
  scripts/setup-scheduled-tasks.sh \
  ; do
  assert "exists: $f" "[[ -e '$CLAUDE_DIR/$f' ]]"
done

# 2. Executable bits
echo ""
echo "--- executable bits ---"
for f in \
  statusline/statusline.py \
  evals/_runner/run.sh evals/_runner/detect.py \
  hooks/auto-verify-on-complete.sh hooks/completion-claim-detector.sh \
  hooks/auto-critic-on-commit.sh hooks/auto-eval-on-agent-edit.sh \
  hooks/log-cache-stats.sh hooks/_log_cache_stats.py hooks/verify-gate.sh \
  hooks/session-start-knowledge.sh \
  rl/emit_task_reward.py rl/emit_correction_signal.py rl/emit_session_rewards.py \
  rl/best_of_n.py rl/ab_test.py rl/usc.py rl/aspect_panel.py \
  scripts/setup-scheduled-tasks.sh \
  ; do
  assert "executable: $f" "[[ -x '$CLAUDE_DIR/$f' ]]"
done

# 3. Python imports
echo ""
echo "--- python imports ---"
for mod_dir in \
  rl:best_of_n rl:ab_test rl:usc rl:aspect_panel \
  rl:emit_task_reward rl:emit_correction_signal rl:emit_session_rewards \
  hooks:_log_cache_stats \
  evals/_runner:detect \
  ; do
  d="${mod_dir%%:*}"
  m="${mod_dir##*:}"
  assert "imports: $d/$m" "python3 -c 'import sys; sys.path.insert(0, \"$CLAUDE_DIR/$d\"); import $m'"
done

# 4. Statusline real-schema
echo ""
echo "--- statusline real-schema ---"
SL_OUT="$(echo '{"model":{"id":"claude-opus-4-7"},"session":{"input_tokens":1000,"cache_read_input_tokens":8500,"cache_creation_input_tokens":500,"context_pct":35.2,"total_cost_usd":0.42,"output_tokens":234}}' | python3 "$CLAUDE_DIR/statusline/statusline.py" 2>/dev/null || true)"
assert "statusline contains 'opus'" "echo '$SL_OUT' | grep -q opus"
assert "statusline contains '85%' (cache hit rate)" "echo '$SL_OUT' | grep -q '85%'"
assert "statusline contains '0.42' (cost)" "echo '$SL_OUT' | grep -q '0.42'"

# 5. log-cache-stats real-schema
echo ""
echo "--- log-cache-stats real-schema ---"
TEST_DIR="$(mktemp -d)"
TEST_HOME="$TEST_DIR/fakehome"
mkdir -p "$TEST_HOME/.claude"
HOME="$TEST_HOME" \
  bash -c "echo '{\"session_id\":\"smoke\",\"model\":{\"id\":\"claude-opus-4-7\"},\"input_tokens\":1000,\"output_tokens\":234,\"cache_read_input_tokens\":8500,\"cache_creation_input_tokens\":500,\"total_cost_usd\":0.42,\"terminal_reason\":\"completed\"}' | python3 '$CLAUDE_DIR/hooks/_log_cache_stats.py'"
assert "cache-stats.jsonl record written" "[[ -f $TEST_HOME/.claude/telemetry/cache-stats.jsonl ]] && grep -q smoke $TEST_HOME/.claude/telemetry/cache-stats.jsonl"
assert "hit_rate computed correctly (0.85)" "tail -1 $TEST_HOME/.claude/telemetry/cache-stats.jsonl | python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); sys.exit(0 if abs(r[\"cache_hit_rate\"]-0.85)<0.001 else 1)'"
rm -rf "$TEST_DIR"

# 6. Eval scenarios authored
echo ""
echo "--- eval scenarios authored ---"
n="$(ls "$CLAUDE_DIR"/evals/scenarios/verifier/*.md 2>/dev/null | wc -l | tr -d ' ')"
assert "≥5 verifier scenarios" "[[ $n -ge 5 ]]"

# 7. Settings template valid JSON (against our repo's template — not user's stale file)
REPO_TEMPLATE="$(dirname "$(dirname "${BASH_SOURCE[0]}")")/claude/settings.json.template"
if [[ -f "$REPO_TEMPLATE" ]]; then
  assert "repo settings.json.template is valid JSON" "python3 -c 'import json; json.load(open(\"$REPO_TEMPLATE\"))'"
fi

# Phase H smoke (delegate)
echo ""
echo "--- Phase H ---"
SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
if [[ -x "$SCRIPT_DIR/phase_h_smoke.sh" ]]; then
  if CLAUDE_DIR="$CLAUDE_DIR" bash "$SCRIPT_DIR/phase_h_smoke.sh" >/dev/null 2>&1; then
    PASS=$((PASS+1))
    T+=("✓ Phase H smoke (delegated)")
  else
    FAIL=$((FAIL+1))
    T+=("✗ Phase H smoke (run ./tests/phase_h_smoke.sh standalone for detail)")
  fi
fi

# Summary
echo ""
echo "=========================================="
echo "Smoke test: $PASS passed, $FAIL failed"
echo "=========================================="
for line in "${T[@]}"; do echo "$line"; done
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
