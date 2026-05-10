# Next Steps — Post-Build Plan

> Captured at the end of the build sprint (2026-05-10) so the plan survives the session. Order matters.

## Status as of last build

- **Repo**: 16 skills, 20 agents, 10 hooks, 8 RL scripts, full SCRUM team, AggAgent synthesis, sandbox, exec-grounded BoN, multi-modal verifier, adversarial audit, RL telemetry, knowledge memory.
- **CI**: 9 commits, all green.
- **Bench**: py-001 (pagination off-by-one) + py-002 (CSV parser, deterministic failures) installed.
- **Scheduled tasks**: 3 created (daily cache-report, weekly mine-transcripts, weekly rl-status).
- **Validation**: orchestration proven E2E via `loop_demo.sh` and `scrum-e2e-demo/demo.sh`. Real-API validation pending.
- **Blocker**: Anthropic subscription rate-limited until **May 14 at 2pm ET**.

## Step 1 — Validation pass (after May 14)

When the rate limit clears, run this in order. Total cost ~$10-30, ~30 minutes.

```bash
# 1. Confirm quota cleared
echo "ping" | claude -p --max-turns 1 --max-budget-usd 0.01 --output-format json | jq .is_error
# Expect: false

# 2. /verify on a trivial example
echo "Use the verifier agent to verify that ~/.claude/sandbox/sandbox_run.py exits 0 with --help" \
  | claude -p --max-turns 5 --max-budget-usd 0.10
# Expect: RESULT_verifier=PASS in output

# 3. /eval on the verifier scenarios
~/.claude/evals/_runner/run.sh verifier
# Expect: 5 scenarios run, scoring report

# 4. The actual SWE-bench mini run
cd ~/Documents/claude-code-teams/bench/swe-bench-mini
./run.sh --all --n 3
python3 score.py runs/$(ls -t runs/ | head -1)
# Expect: empirical pass@1 number to compare against LIVE-SWE-AGENT 77.4%

# 5. Real /scrum on a tiny goal (use a throwaway dir)
mkdir -p /tmp/scrum-test && cd /tmp/scrum-test
echo "Run /scrum with this goal: 'create a single Python function that validates email addresses, with 5 tests covering happy path + 4 edge cases. Place at email_validator.py + tests.py'" \
  | claude -p --max-turns 30 --max-budget-usd 5.00
# Expect: stories.md, design.md, plan.md, evidence/, audit.md, retro.md generated; audit verdict PASS

# 6. /aspect-panel on a real diff
cd ~/some-git-repo-with-uncommitted-changes
echo "Run /aspect-panel against the current uncommitted diff" | claude -p --max-budget-usd 1.00
# Expect: 5 verdict lines (correctness, edge-case, security, regression, style) with pass_share

# 7. /mine-transcripts on the last 7 days
echo "Run /mine-transcripts 7d. Surface what was found." | claude -p --max-budget-usd 3.00
# Expect: telemetry/mining-runs/<ts>/ with extractions, lessons.diff, agent-tuning.md
```

If any of these fail, capture stderr + decision.json + agent transcripts. The most likely failures:
- Agent doesn't emit `RESULT_<name>=` last line → fix the agent prompt
- Schema mismatch on the API response → fix the parser
- Auth/budget issue → adjust flags
- Hook not firing → check `~/.claude/telemetry/`

## Step 2 — Dogfood on a real project (after Step 1 passes)

Pick ONE of your projects: Shipwright, aim, h-uman, pocket-voice. Pick a real bug or small feature. Run `/scrum` against it.

```bash
cd ~/Documents/<project>
echo "/scrum '<actual goal — one paragraph>'" | claude -p --max-budget-usd 20
```

Watch for:
- Did the PO refuse the goal as too vague? (Good — that's the design.)
- Did the tech-lead correctly identify the cheapest design?
- Did the implementer rollouts make sensible edits?
- Did the verifier actually run the test command, or hallucinate?
- Did the auditor catch any drift between AC and shipped?

Capture every one of these as a finding. They are the next priorities to fix.

## Step 3 — Let the cron run (already configured)

3 scheduled tasks are installed:
- **Daily 9:21am**: `/cache-report` (silent unless cache hit rate <70% or cost spike)
- **Weekly Mon 9:21am**: `/mine-transcripts 7d` (notify with summary)
- **Weekly Mon 9:31am**: `/rl-status` (notify with flagged agents)

Verify they're firing:
```bash
ls ~/.claude/scheduled-tasks/
# Expect: daily-cache-report/  weekly-mine-transcripts/  weekly-rl-status/
```

After ~7 days of real activity:
- `~/.claude/telemetry/cache-stats.jsonl` should have ≥7 records
- `~/.claude/rl/rewards.jsonl` should have ≥10 records (from real TaskCompleted events)
- `~/.claude/rl/value/<agent>.json` should populate beyond synthetic tests
- `~/.claude/lessons.md` may get appended via mine-transcripts

After ~30 days:
- `/rl-status` should flag specific agents (low reward variance)
- `/mine-transcripts` should have proposed real lesson diffs

## Step 4 — Build based on observed gaps

Only AFTER Steps 1-3 yield real signal, build the next thing. Candidates ranked by research-evidence × cost-to-build:

### Tier I (build if real usage exposes the gap)
1. **Tree-sitter repo-map with PageRank** (Aider, +30-50% on unfamiliar repos). Pure engineering. ~1 day.
2. **HCAPO counterfactual critic** (arXiv 2603.08754, +7-13% step-credit). Prompt-only. ~1 week.
3. **Trajectory-Informed Memory** (arXiv 2603.10600, +14-28pp on AppWorld). Schema upgrade to lessons.md. ~1-2 days.
4. **Per-tool shadow checkpoints** (Cline). PostToolUse hook + git stash. ~half day.
5. **Architect/Editor model split** (Aider). Pipeline template. ~1 day.

### Tier II (deferred until usage data justifies)
- **Conditional aspect-panel** (cheap rubric → escalate). Wait until aspect-panel invocation count > 10.
- **Per-agent effort routing via RL telemetry**. Wait until rewards.jsonl has ≥50 events per agent.
- **In-loop typecheck after Edit** (Copilot pattern). Wait until "agent edits, breaks build" pattern observed.
- **OTel trace emission**. Build when fleet observability becomes pressing.

### Tier III (specialized)
- **SWE-bench Verified integration with official Docker harness**. After Step 1's pass@1 number is reasonable.
- **Dependency-graph-as-context** (r/ClaudeCode 65% token reduction). Pure engineering, but requires repo-map first.

## Step 5 — Public launch (optional)

When the system has 30+ days of real signal:
- Update `README.md` with actual measured numbers (cache hit rate, agent reward distributions, SWE-bench mini pass@1).
- Write a launch post. Linkable evidence > theoretical claims.
- Submit to awesome-claude-code, share on Twitter/X with concrete numbers.
- Pre-existing repos to learn from: `obra/superpowers`, `dsifry/metaswarm`, `wshobson/agents`.

## Things NOT to do

- **Don't build more components before Step 1.** Every "expected gain" claim is hypothetical until validated.
- **Don't run `/scrum` on a critical project** as the first dogfood. Use a sandbox project. Real failures will be loud.
- **Don't treat "tests pass" as `done` for high-stakes work** — the adversarial audit exists specifically to catch this.
- **Don't disable hooks** (verify-gate, auto-verify, constitutional-gate) "just to ship faster". They're the load-bearing pieces.
- **Don't trust the published gains in the research.** They were measured on different stacks. Our numbers will differ.

## Quick reference

| | Where |
|---|---|
| Repo | `~/Documents/claude-code-teams/` |
| Public mirror | `github.com/sethdford/claude-code-teams` |
| Installed location | `~/.claude/` |
| Telemetry | `~/.claude/telemetry/` |
| RL state | `~/.claude/rl/` |
| Scheduled tasks | `~/.claude/scheduled-tasks/` |
| Validation script | `tests/smoke.sh` |
| E2E SCRUM demo | `bench/scrum-e2e-demo/demo.sh` |
| SOTA proof doc | `SOTA_FINAL.md` |
| arXiv references | `docs/arxiv-references.md` |

## When in doubt

Re-read this doc, run `tests/smoke.sh`, and check `~/.claude/telemetry/cache-stats.jsonl` for recent activity. If nothing's been logged in 24h, the hooks aren't firing — restart Claude Code.
