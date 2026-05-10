---
name: exec-grounded
description: Run an agent N times in parallel against a code-change task, with each rollout in its own sandboxed copy of the codebase, scored by ACTUAL test pass rate (not just critic opinion). Use for SWE-bench-style code changes where the test suite is the ground truth. Triggers on /exec-grounded, "execution-grounded", "verify by running tests", "best-of-N with tests".
when_to_use: When you have a clear test command and a code change to implement. The test suite IS the verifier — agent rollouts that don't make tests green get scored down. Top SWE-bench leaders spend 60-80% of compute on this kind of verification.
allowed-tools: Bash, Read
arguments: [agent, prompt, target-dir, test-cmd, n]
---

# /exec-grounded — Best-of-N where tests decide

`/exec-grounded <agent> "<prompt>" --target-dir <dir> --test-cmd "<cmd>" [--n 3]`

Mirrors the SWE-bench-leader pattern: each candidate is **executed**, not just judged. The test exit code is the dominant signal (0.7 weight); critic score is the tiebreaker (0.3).

## How

```bash
python3 ~/.claude/rl/exec_grounded.py <agent> "<prompt>" \
  --target-dir ./src \
  --test-cmd "pytest -q" \
  --n 3
```

Per rollout:
1. **Stage**: `cp -r ./src /tmp/bon-<ts>/work-<idx>/` (skips node_modules, .git, __pycache__, etc.)
2. **Run**: Claude works in `/tmp/bon-<ts>/work-<idx>/` (passed via `--add-dir`); makes whatever edits the agent decides
3. **Verify in sandbox**: `sandbox_run.py --cwd <workdir> -- <test-cmd>` — OS-level isolation (no writes outside workdir, no network unless `--allow-network`)
4. **Parse test output**: pytest / jest / vitest / go test patterns recognized; falls back to exit-code check
5. **Score**: `test_score * 0.7 + critic_score * 0.3`
   - `test_score = 1.0` (all green), `-1.0` (all red), `0.0` (no tests found), `(passed - failed)/total` (partial)
   - `critic_score`: parsed from `RESULT_critic=CLEAN|HAS_FINDINGS_n_n` if present

## Output

```json
{
  "n": 3,
  "winner_idx": 1,
  "winner_score": 0.85,
  "winner_test_stats": {"passed": 12, "failed": 0, "total": 12, "runner": "pytest"},
  "spread": 1.10,
  "out_dir": "~/.claude/rl/exec-grounded-runs/<ts>"
}
```

`out_dir/decision.json` has the full per-rollout breakdown including stdout/stderr excerpts. The winner's `workdir` is preserved for inspection or merging back.

## Test runners recognized

- **pytest**: `N passed, M failed, K errors in T s`
- **jest** / **vitest**: `Tests: A failed, B passed, C total`
- **go test**: `--- PASS:` / `--- FAIL:` line counts

For other runners (rspec, mocha, cargo test), the test_score falls back to exit-code-only (1.0 if exit 0, 0.0 otherwise). Add a parser to `parse_test_output` in `rl/exec_grounded.py` to extend.

## Cost discipline

- N rollouts × `--max-budget-usd` (default $1) = up to $N total per call
- Plus N test runs (typically <$0.001 each — they're local subprocess)
- Budget gate via `--max-budget-usd 0.30` per rollout for routine use

## When NOT to use

- No test suite (`/exec-grounded` collapses to plain best-of-N — use that instead)
- Test suite takes >5 minutes (sandbox timeout is 600s; one slow run blocks parallelism)
- Single-line trivial fix (overhead > value)
- Tests have no isolation (e.g., they hit a real DB you can't sandbox-network) — surface failure mode

## Anti-patterns

- Setting `--allow-network` on every run — defeats the isolation
- Running with N=8 by default — 3 is a strong baseline; escalate only if disagreement is high
- Treating green tests as final correctness — tests can be incomplete; pair with `/aspect-panel` on the winner's diff for a second read
- Picking the rollout by `score` and then trying to merge by hand — the `winner.workdir` IS the change; copy from there
