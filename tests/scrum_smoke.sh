#!/usr/bin/env bash
# SCRUM E2E smoke — runs the bench/scrum-e2e-demo in both modes.
PASS=0; FAIL=0; T=()
assert() { if eval "$2"; then PASS=$((PASS+1)); T+=("✓ $1"); else FAIL=$((FAIL+1)); T+=("✗ $1"); fi; }
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
REPO_DIR="$(dirname "$(dirname "${BASH_SOURCE[0]}")")"

# 1. Files in place
for f in product-owner scrum-master tech-lead sprint-auditor; do
  assert "agent: $f exists" "[[ -f $CLAUDE_DIR/agents/$f.md ]]"
done
assert "/scrum skill exists" "[[ -f $CLAUDE_DIR/skills/scrum/SKILL.md ]]"
assert "scrum-e2e-demo exists" "[[ -x $REPO_DIR/bench/scrum-e2e-demo/demo.sh ]]"

# 2. Each agent ends with RESULT_<name>= contract line
for f in product-owner scrum-master tech-lead sprint-auditor; do
  assert "$f.md has RESULT_ contract" "grep -q 'RESULT_$f=' $CLAUDE_DIR/agents/$f.md"
done

# 3. NORMAL mode passes
NORMAL_OUT="$($REPO_DIR/bench/scrum-e2e-demo/demo.sh 2>&1 || true)"
assert "demo NORMAL exits with PASS verdict" "echo \"\$NORMAL_OUT\" | grep -q 'Sprint CLOSED — all ACs delivered'"

# 4. BREAK-IT mode catches drift
BREAK_OUT="$($REPO_DIR/bench/scrum-e2e-demo/demo.sh --break-it 2>&1 || true)"
assert "demo BREAK-IT catches drift" "echo \"\$BREAK_OUT\" | grep -q 'Sprint BLOCKED'"
assert "demo BREAK-IT cites the specific drift" "echo \"\$BREAK_OUT\" | grep -qi 'drift'"

echo ""
echo "SCRUM smoke: $PASS passed, $FAIL failed"
for line in "${T[@]}"; do echo "$line"; done
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
