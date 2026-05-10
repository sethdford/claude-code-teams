#!/usr/bin/env bash
# SCRUM full-ceremony E2E demo. No Claude API required.
# Each "agent" output is simulated; the verifier and auditor are REAL deterministic logic.
#
# Demonstrates:
#   - stories.md / designs / plan / review / audit / retro state files
#   - Role-to-role data flow (PO → TL → SM → impl → verifier → auditor → retro)
#   - Real sandboxed pytest as the verifier
#   - Deterministic auditor parses AC and checks code state independently
#   - Definition of Done enforcement
#
# Usage:
#   ./demo.sh                  (runs against a clean copy of py-001 + py-002)
#   ./demo.sh --break-it       (introduces a partial fix to show audit catches drift)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Use CLAUDE_DIR if set (CI mode); fall back to home install
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SR="$CLAUDE_DIR/sandbox/sandbox_run.py"
# If sandbox runner not found at CLAUDE_DIR, try the repo's own copy
if [[ ! -x "$SR" ]] && [[ -x "$REPO_ROOT/claude/sandbox/sandbox_run.py" ]]; then
  SR="$REPO_ROOT/claude/sandbox/sandbox_run.py"
fi
SPRINT_DIR=$(mktemp -d -t scrum-demo-XXXXXX)
SPRINT_NUM=1
N=$SPRINT_NUM

BREAK_IT=0
[[ "${1:-}" == "--break-it" ]] && BREAK_IT=1

echo "=== SCRUM E2E Demo ==="
echo "Sprint dir: $SPRINT_DIR"
echo "Mode: $([[ $BREAK_IT -eq 1 ]] && echo 'BREAK-IT (audit should catch the drift)' || echo 'NORMAL (audit should pass)')"
echo ""

mkdir -p "$SPRINT_DIR/sprints/sprint-$N"/{designs,evidence,workdirs}
SPRINT="$SPRINT_DIR/sprints/sprint-$N"

# ─── Phase 1: PRODUCT OWNER ─────────────────────────────────────────────
echo "▶ Phase 1: Product Owner authors stories"
cat > "$SPRINT/stories.md" <<'EOF'
# Sprint 1 Backlog

## Goal
Fix two known bugs in the bench/swe-bench-mini fixtures so they ship green.

## User Stories (in priority order)

### US-1 (P0): As a developer, I want pagination.next_page to return correct slices, so that paged listing works on boundary cases.
**Acceptance criteria:**
- AC-1.1: next_page(items, page_index, page_size) returns items[page_index*page_size:(page_index+1)*page_size]
- AC-1.2: Returns empty list when page_index is past end
- AC-1.3: Raises ValueError on negative page_index OR page_size <= 0
- AC-1.4: All 8 tests in tasks/py-001/repo/tests.py pass
**Estimate:** S
**Priority:** P0
**Dependencies:** none
**DoD:** tests pass, /verify pass, /aspect-panel CLEAN

### US-2 (P1): As a developer, I want Counter.increment to be thread-safe, so that concurrent increments don't lose updates.
**Acceptance criteria:**
- AC-2.1: increment() is atomic across threads
- AC-2.2: 1000 concurrent increments from 10 threads produce final value 1000
- AC-2.3: All 3 tests in tasks/py-002/repo/tests.py pass
**Estimate:** S
**Priority:** P1
**Dependencies:** none
**DoD:** tests pass, /verify pass

## Non-goals
- We will NOT change the public API of either module
- We will NOT add new dependencies

RESULT_product-owner=READY
EOF
echo "  ✓ wrote $SPRINT/stories.md (2 stories, 7 ACs)"

# ─── Phase 2: TECH LEAD ─────────────────────────────────────────────────
echo ""
echo "▶ Phase 2: Tech Lead designs"
cat > "$SPRINT/designs/US-1.md" <<'EOF'
# Design for US-1: pagination off-by-one

## Approach
Replace `end = (page_index + 1) * page_size - 1` with `end = (page_index + 1) * page_size`. Python slicing is half-open; the -1 truncates by one. Keep validation guards intact.

## Files to modify
| File | Change | LOC |
|---|---|---|
| pagination.py | fix end calculation | -1 +1 |

## Implementation steps
1. Open pagination.py
2. Change `end = (page_index + 1) * page_size - 1` → `end = (page_index + 1) * page_size`
3. Run pytest tests.py — all 8 should pass

## Risks
- (LOW/SMALL) Backward compat: the function was returning truncated pages; any caller that expected this would have been broken already. Mitigation: none needed.

## AC mapping
- AC-1.1 → end calculation correctness
- AC-1.2, AC-1.3 → existing guard branches preserved
- AC-1.4 → tests.py is canonical

RESULT_tech-lead=DESIGN_READY
EOF
cat > "$SPRINT/designs/US-2.md" <<'EOF'
# Design for US-2: Counter thread-safety

## Approach
Wrap the read-modify-write in `threading.Lock()`. Smallest reversible change.

## Files to modify
| File | Change | LOC |
|---|---|---|
| counter.py | add Lock + with-block | +3 |

## Implementation steps
1. Import threading
2. Initialize self._lock = threading.Lock() in __init__
3. Wrap increment body in `with self._lock:`
4. Run tests — concurrent test should pass

## Risks
- (LOW/SMALL) Performance: lock contention under heavy concurrent writes. Acceptable for this use case.

## AC mapping
- AC-2.1, AC-2.2 → lock provides atomicity
- AC-2.3 → existing tests pass

RESULT_tech-lead=DESIGN_READY
EOF
echo "  ✓ wrote 2 design docs"

# ─── Phase 3: SCRUM MASTER plan ────────────────────────────────────────
echo ""
echo "▶ Phase 3: Scrum Master writes wave plan"
cat > "$SPRINT/plan.md" <<'EOF'
# Sprint 1 Plan

## Sequencing
Wave 1 (parallel): US-1, US-2 (independent files)

## Assignments
- US-1 → general-purpose, isolation: worktree, model: sonnet
- US-2 → general-purpose, isolation: worktree, model: sonnet

## DoD per story (enforced)
- /verify returns RESULT_verifier=PASS
- /aspect-panel returns PASS or CLEAN (not ESCALATE)
- No outstanding RESULT_critic=HAS_FINDINGS_CRITICAL

RESULT_scrum-master=PLAN_READY
EOF
echo "  ✓ wrote plan.md"

# ─── Phase 4: IMPLEMENTERS (simulated) ─────────────────────────────────
echo ""
echo "▶ Phase 4: Implementers fix the bugs (simulated successful rollouts)"

# Stage workdirs (mirrors exec_grounded.stage_workdir)
mkdir -p "$SPRINT/workdirs/US-1" "$SPRINT/workdirs/US-2"
cp -r "$REPO_ROOT/bench/swe-bench-mini/tasks/py-001/repo/." "$SPRINT/workdirs/US-1/"
cp -r "$REPO_ROOT/bench/swe-bench-mini/tasks/py-002/repo/." "$SPRINT/workdirs/US-2/"

# Apply US-1 fix
cat > "$SPRINT/workdirs/US-1/pagination.py" <<'EOF'
"""Pagination helper - bug fixed."""

def next_page(items, page_index, page_size=10):
    if page_index < 0:
        raise ValueError("page_index must be >= 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    return items[page_index * page_size:(page_index + 1) * page_size]
EOF
echo "  ✓ US-1 fix applied"

# Apply US-2 fix (or not, in --break-it mode)
if [[ $BREAK_IT -eq 1 ]]; then
  # PARTIAL fix: implementer "forgot" to actually use the lock — looks correct but isn't
  cat > "$SPRINT/workdirs/US-2/counter.py" <<'EOF'
"""Counter - PARTIAL fix (lock created but never used — adversarial test)."""
import threading

class Counter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()  # created but never acquired
    def increment(self):
        # Still racy — agent forgot the with-block
        current = self._value
        self._value = current + 1
        return self._value
    def get(self): return self._value
    def reset(self): self._value = 0
EOF
  echo "  ⚠ US-2 has a PARTIAL fix (audit should catch it)"
else
  cat > "$SPRINT/workdirs/US-2/counter.py" <<'EOF'
"""Counter - thread-safe."""
import threading

class Counter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()
    def increment(self):
        with self._lock:
            self._value += 1
            return self._value
    def get(self): return self._value
    def reset(self):
        with self._lock:
            self._value = 0
EOF
  echo "  ✓ US-2 fix applied"
fi

# ─── Phase 5: VERIFIER (REAL — sandboxed pytest) ───────────────────────
echo ""
echo "▶ Phase 5: Verifier runs tests in sandbox (REAL execution)"

run_verifier() {
  local us="$1" workdir="$2"
  mkdir -p "$SPRINT/evidence/$us"
  python3 "$SR" --cwd "$workdir" --json -- python3 -m pytest tests.py -q \
    > "$SPRINT/evidence/$us/verifier.json" 2>&1 || true

  EG_PATH="$CLAUDE_DIR/rl/exec_grounded.py"
  if [[ ! -f "$EG_PATH" ]] && [[ -f "$REPO_ROOT/claude/rl/exec_grounded.py" ]]; then
    EG_PATH="$REPO_ROOT/claude/rl/exec_grounded.py"
  fi
  python3 - "$SPRINT/evidence/$us/verifier.json" "$EG_PATH" <<'PYEOF'
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("eg", sys.argv[2])
eg = importlib.util.module_from_spec(spec); spec.loader.exec_module(eg)
r = json.load(open(sys.argv[1]))
stats = eg.parse_test_output(r['stdout'], r['stderr'])
print(f"  {stats['passed']}/{stats['total']} passed | exit {r['exit_code']} | sandbox: {r['sandbox_mechanism']}")
result = "PASS" if r['exit_code'] == 0 and stats['failed'] == 0 else "FAIL"
print(f"  RESULT_verifier={result}")
PYEOF
}

echo "  US-1 verifier:"; run_verifier US-1 "$SPRINT/workdirs/US-1"
echo "  US-2 verifier:"; run_verifier US-2 "$SPRINT/workdirs/US-2"

# ─── Phase 6: SCRUM MASTER review ──────────────────────────────────────
echo ""
echo "▶ Phase 6: Scrum Master generates review"
cat > "$SPRINT/review.md" <<EOF
# Sprint 1 Review

## Stories shipped
EOF
for us in US-1 US-2; do
  result=$(grep -oE "RESULT_verifier=(PASS|FAIL|INCONCLUSIVE)" "$SPRINT/evidence/$us/verifier.json" 2>/dev/null | tail -1 || echo "RESULT_verifier=UNKNOWN")
  v=$(echo "$result" | cut -d= -f2)
  echo "| $us | $v | evidence/$us/verifier.json |" >> "$SPRINT/review.md"
done
echo "RESULT_scrum-master=REVIEW_READY" >> "$SPRINT/review.md"
echo "  ✓ wrote review.md"

# ─── Phase 7: SPRINT AUDITOR (REAL deterministic audit) ────────────────
echo ""
echo "▶ Phase 7: Sprint Auditor (independent, deterministic)"
python3 - "$SPRINT" <<'PYEOF'
import json, re, subprocess, os, sys
from pathlib import Path

sprint = Path(sys.argv[1])
stories = (sprint / "stories.md").read_text()
audit_lines = ["# Sprint 1 Audit (deterministic)\n"]

# Parse AC list
acs_by_story = {}
current = None
for line in stories.splitlines():
    m = re.match(r"^### (US-\d+)", line)
    if m:
        current = m.group(1)
        acs_by_story[current] = []
    m = re.match(r"^- (AC-[\d.]+):\s*(.+)$", line)
    if m and current:
        acs_by_story[current].append((m.group(1), m.group(2)))

# Audit each AC
total_acs = sum(len(v) for v in acs_by_story.values())
delivered = 0
findings = []

for us, acs in acs_by_story.items():
    workdir = sprint / "workdirs" / us
    audit_lines.append(f"\n## {us}")
    for ac_id, ac_text in acs:
        # Check verifier evidence: did tests pass?
        ev = sprint / "evidence" / us / "verifier.json"
        if not ev.exists():
            audit_lines.append(f"- {ac_id}: MISSED — no verifier evidence")
            findings.append(f"{us}/{ac_id}: missing evidence")
            continue
        v = json.loads(ev.read_text())
        if v.get("exit_code") != 0:
            audit_lines.append(f"- {ac_id}: MISSED — verifier exit {v['exit_code']}")
            findings.append(f"{us}/{ac_id}: verifier failed")
            continue
        # Adversarial: spot-check the implementation matches the AC intent
        if "thread-safe" in ac_text.lower() or "atomic" in ac_text.lower():
            counter_py = (workdir / "counter.py").read_text() if (workdir / "counter.py").exists() else ""
            # Find the increment method body and check if it acquires the lock
            inc_match = re.search(r"def increment\(self.*?\):(.*?)(?=\n    def |\Z)", counter_py, re.DOTALL)
            inc_body = inc_match.group(1) if inc_match else ""
            if "with self._lock" not in inc_body and "self._lock.acquire" not in inc_body:
                audit_lines.append(f"- {ac_id}: DRIFT — increment() does not acquire self._lock; tests may pass on CPython GIL but the AC is not semantically satisfied")
                findings.append(f"{us}/{ac_id}: drift — increment() body lacks lock acquisition (looks safe but isn't)")
                continue
        delivered += 1
        audit_lines.append(f"- {ac_id}: DELIVERED — verifier exit 0; code state checked")

# Verdict
audit_lines.append(f"\n## Summary")
audit_lines.append(f"Total ACs: {total_acs}")
audit_lines.append(f"Delivered: {delivered}")
audit_lines.append(f"Findings: {len(findings)}")
audit_lines.append("")
if findings:
    audit_lines.append("## Findings")
    for f in findings: audit_lines.append(f"- {f}")
    audit_lines.append("")
    # FAIL: missing evidence, failed verifier, or DRIFT (adversarial finding).
    # PASS_WITH_NOTES: only soft issues like missing tests for a delivered behavior.
    severe_keywords = ("missing", "failed", "drift", "missed")
    is_severe = any(any(kw in f.lower() for kw in severe_keywords) for f in findings)
    verdict = "FAIL" if is_severe else "PASS_WITH_NOTES"
else:
    verdict = "PASS"
audit_lines.append(f"RESULT_sprint-auditor={verdict}")

(sprint / "audit.md").write_text("\n".join(audit_lines))
print(f"  Audit verdict: {verdict}")
print(f"  Delivered: {delivered}/{total_acs} ACs")
if findings:
    print(f"  Findings:")
    for f in findings:
        print(f"    - {f}")
PYEOF

# ─── Phase 8: RETRO ────────────────────────────────────────────────────
echo ""
echo "▶ Phase 8: Retro"
audit_verdict=$(grep -oE "RESULT_sprint-auditor=\w+" "$SPRINT/audit.md" | cut -d= -f2)
cat > "$SPRINT/retro.md" <<EOF
# Sprint 1 Retro

## Audit verdict
$audit_verdict

## What worked
- Sandboxed verifier caught real failures
- Deterministic auditor parses ACs and re-checks against code state
- DoD enforced: stories not closed without verifier PASS

## What broke
$(if [[ "$audit_verdict" == "FAIL" ]]; then echo "- Audit detected drift; sprint cannot close. Stories re-opened."; else echo "- (none)"; fi)

## Next sprint
- Continue using /scrum for multi-story work
- Watch for adversarial patterns: tests passing on CPython GIL despite missing locks
EOF
echo "  ✓ wrote retro.md"

# ─── Final summary ─────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "Sprint $N Summary"
echo "=========================================="
echo "Verdict: $audit_verdict"
echo "Sprint dir: $SPRINT_DIR"
echo ""
echo "Files generated:"
find "$SPRINT" -type f | sed 's|'"$SPRINT_DIR"'/|  |'
echo ""
case "$audit_verdict" in
  PASS)
    echo "✅ Sprint CLOSED — all ACs delivered, no findings."
    exit 0 ;;
  PASS_WITH_NOTES)
    echo "✅ Sprint CLOSED with notes — minor findings recorded for next sprint."
    exit 0 ;;
  FAIL)
    echo "❌ Sprint BLOCKED — audit caught drift / missed AC. Stories would re-open in a real run."
    echo "   See: $SPRINT/audit.md for the specific findings."
    exit 1 ;;
  INCONCLUSIVE)
    echo "⚠ Sprint INCONCLUSIVE — auditor could not complete. Surface to user."
    exit 2 ;;
  *)
    echo "Unknown verdict: $audit_verdict"
    exit 3 ;;
esac
