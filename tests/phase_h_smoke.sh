#!/usr/bin/env bash
# Phase H smoke (sandbox, exec-grounded, skill-proposer, verify-ui)
PASS=0; FAIL=0; T=()
assert() { if eval "$2"; then PASS=$((PASS+1)); T+=("✓ $1"); else FAIL=$((FAIL+1)); T+=("✗ $1"); fi; }
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

# File presence + executability
assert "sandbox_run.py executable"          "[[ -x $CLAUDE_DIR/sandbox/sandbox_run.py ]]"
assert "exec_grounded.py executable"        "[[ -x $CLAUDE_DIR/rl/exec_grounded.py ]]"
assert "skill_proposer.py executable"       "[[ -x $CLAUDE_DIR/skills/mine-transcripts/skill_proposer.py ]]"
assert "exec-grounded skill present"        "[[ -f $CLAUDE_DIR/skills/exec-grounded/SKILL.md ]]"
assert "verify-ui skill present"            "[[ -f $CLAUDE_DIR/skills/verify-ui/SKILL.md ]]"
assert "verifier agent has sandbox section" "grep -q 'Sandboxed execution' $CLAUDE_DIR/agents/verifier.md"
assert "exec_grounded imports"              "python3 -c 'import sys; sys.path.insert(0, \"$CLAUDE_DIR/rl\"); import exec_grounded'"
assert "skill_proposer imports"             "python3 -c 'import sys; sys.path.insert(0, \"$CLAUDE_DIR/skills/mine-transcripts\"); import skill_proposer'"

# Test parser via standalone python (avoids bash quoting issues)
PARSER_TEST=$(python3 - "$CLAUDE_DIR" <<'PY'
import sys, importlib.util
clauded = sys.argv[1]
spec = importlib.util.spec_from_file_location("eg", f"{clauded}/rl/exec_grounded.py")
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)
ok = True
for runner_name, text, exp_p, exp_f in [
    ("jest",    "Tests: 1 failed, 5 passed, 6 total", 5, 1),
    ("pytest",  "=== 12 passed in 0.4s ===",          12, 0),
    ("pytest2", "=== 8 passed, 2 failed in 1s ===",   8,  2),
    ("vitest",  "Tests: 0 failed, 7 passed, 7 total", 7,  0),
]:
    r = eg.parse_test_output(text, "")
    if r["passed"] != exp_p or r["failed"] != exp_f:
        ok = False
        print(f"FAIL {runner_name}: got passed={r['passed']} failed={r['failed']}, want {exp_p}/{exp_f}")
print("OK" if ok else "FAIL_PARSER")
PY
)
assert "parser handles jest + pytest + vitest" "[[ '$PARSER_TEST' == *'OK'* ]]"

echo ""
echo "Phase H smoke: $PASS passed, $FAIL failed"
for line in "${T[@]}"; do echo "$line"; done
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
