#!/usr/bin/env bash
# SWE-bench Mini — orchestrates per-task runs of the Phase H stack.
# For each task: spawn /exec-grounded with the task's test_cmd, capture pass/fail,
# log cost + wall time, summarize.
#
# Usage:
#   ./run.sh py-001                  # single task
#   ./run.sh --all                   # all tasks
#   ./run.sh py-001 py-002 --n 5     # specific tasks with N rollouts each

set -euo pipefail

BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS_DIR="$BENCH_DIR/tasks"
RUNS_DIR="$BENCH_DIR/runs"
EXEC_GROUNDED="$HOME/.claude/rl/exec_grounded.py"

if [[ ! -x "$EXEC_GROUNDED" ]]; then
  echo "ERROR: $EXEC_GROUNDED not found or not executable." >&2
  echo "  Did you run ./install.sh from the repo root?" >&2
  exit 1
fi

# Parse args
N=3
TASK_IDS=()
for arg in "$@"; do
  case "$arg" in
    --all) for d in "$TASKS_DIR"/*/; do TASK_IDS+=("$(basename "$d")"); done ;;
    --n) shift_next=1 ;;
    --n=*) N="${arg#--n=}" ;;
    *) if [[ "${shift_next:-0}" == "1" ]]; then N="$arg"; shift_next=0; else TASK_IDS+=("$arg"); fi ;;
  esac
done

if [[ ${#TASK_IDS[@]} -eq 0 ]]; then
  echo "Usage: $0 <task-id> [task-id ...]    (or --all)" >&2
  echo "Available tasks:" >&2
  ls "$TASKS_DIR" 2>/dev/null | sed 's/^/  /' >&2
  exit 2
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUNS_DIR/$TIMESTAMP"
mkdir -p "$RUN_DIR"

echo "=== SWE-bench Mini ==="
echo "Tasks: ${TASK_IDS[*]}"
echo "Rollouts per task: $N"
echo "Run dir: $RUN_DIR"
echo ""

for tid in "${TASK_IDS[@]}"; do
  task_dir="$TASKS_DIR/$tid"
  if [[ ! -d "$task_dir" ]]; then
    echo "  [skip] $tid not found" >&2
    continue
  fi
  if [[ ! -f "$task_dir/task.json" ]]; then
    echo "  [skip] $tid has no task.json" >&2
    continue
  fi

  echo "--- Task: $tid ---"
  prompt="$(python3 -c "
import json
t = json.load(open('$task_dir/task.json'))
print(t['summary'] + chr(10) + chr(10) + 'Bug report: ' + t['bug_report'] + chr(10) + chr(10) + 'Contract:' + chr(10) + chr(10).join('- ' + c for c in t['contract']) + chr(10) + chr(10) + 'Files likely to change: ' + ', '.join(t.get('files_likely_to_change', [])) + chr(10) + chr(10) + 'Fix the bug. Tests will be run via: ' + t['test_cmd'])")"

  test_cmd="$(python3 -c "import json; print(json.load(open('$task_dir/task.json'))['test_cmd'])")"
  budget="$(python3 -c "import json; print(json.load(open('$task_dir/task.json')).get('max_budget_usd', 0.50))")"

  out_dir="$RUN_DIR/$tid"
  mkdir -p "$out_dir"

  start=$(date +%s)
  python3 "$EXEC_GROUNDED" \
    "general-purpose" \
    "$prompt" \
    --target-dir "$task_dir/repo" \
    --test-cmd "$test_cmd" \
    --n "$N" \
    --max-budget-usd "$budget" \
    --out "$out_dir" \
    > "$out_dir/stdout.json" 2> "$out_dir/stderr.log" || echo "  [warn] exec_grounded exited non-zero"
  end=$(date +%s)
  elapsed=$((end - start))

  # Pull headline stats from decision.json
  if [[ -f "$out_dir/decision.json" ]]; then
    python3 -c "
import json
d = json.load(open('$out_dir/decision.json'))
w = d.get('winner') or {}
ts = w.get('test_stats') or {}
print(f'  winner_score={w.get(\"score\")} test_pass={ts.get(\"passed\",0)}/{ts.get(\"total\",0)} time=${elapsed}s')
"
  else
    echo "  [warn] no decision.json — see $out_dir/stderr.log"
  fi
done

echo ""
echo "=== Done. Run dir: $RUN_DIR ==="
echo "Score with: python3 $BENCH_DIR/score.py $RUN_DIR"
