---
name: eval
description: Run evaluations against skills, agents, or rules. Use when the user wants to test that a skill triggers correctly, measure agent output quality, compare prompt variants, or detect regressions. Triggers on /eval, "run evals", "test skill", "benchmark agent".
when_to_use: Run before shipping any new skill or agent change. Run after CLAUDE.md or rule edits. Run on a schedule via /loop to detect regressions.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
arguments: [target]
---

# /eval — Run the Skill/Agent/Rule Eval Harness

`/eval <target>` runs the evaluation suite against `target` (a skill name, agent name, rule file, or "all").

## What gets measured

For each scenario in `~/.claude/evals/scenarios/<target>/*.md`:

1. **Trigger accuracy** (programmatic, deterministic) — did the right skill/agent fire?
2. **Tool-use correctness** (programmatic) — did it call the expected tools?
3. **Output quality** (LLM judge) — does the output match the rubric?
4. **Cost & latency** (programmatic) — token usage, wall time, model used
5. **Regression delta** — vs previous run scored on the same scenarios

## How to invoke

```
/eval verifier             # one agent
/eval team                  # one skill
/eval CLAUDE.md             # the global rules file
/eval all                   # full sweep
/eval all --since 7d        # only targets changed in last 7 days
```

## Workflow you must follow

1. **Resolve the target.** If `target` is "all", glob `~/.claude/evals/scenarios/*/`. Otherwise use `~/.claude/evals/scenarios/$target/`.
2. **List scenarios.** Each scenario is one `.md` file with frontmatter: `prompt`, `expects` (tool calls + skill activations), `rubric`.
3. **Run the harness.** Execute `~/.claude/evals/_runner/run.sh <target>` which invokes `claude -p` headless with `--output-format stream-json --include-partial-messages`, captures the full event stream, and writes results to `~/.claude/evals/runs/<target>/<timestamp>.jsonl`.
4. **Score with judge.** For each scenario, invoke the judge skill (loaded from `~/.claude/evals/_runner/judge.md`) against the captured output and rubric. Programmatic checks first (PASS/FAIL); judge only runs if programmatic passes.
5. **Compute regression delta.** Read the previous run from `~/.claude/evals/runs/<target>/`, compute per-criterion delta. Flag any criterion that regressed by >1 point or new failures.
6. **Write report.** Markdown report to `~/.claude/evals/runs/<target>/<timestamp>.md` with: scenario-by-scenario PASS/FAIL, trigger accuracy %, judge scores, top-3 regressions, top-3 wins.
7. **Print summary.** Print to stdout: target, # scenarios, pass rate, avg judge score, regression count.

## Rubric scoring

Each scenario rubric is a list of weighted criteria, each scored 0–5:

```yaml
rubric:
  - criterion: "calls verifier agent before claiming task complete"
    weight: 3
  - criterion: "captures actual command output, not paraphrase"
    weight: 2
  - criterion: "returns concise summary (<200 words)"
    weight: 1
```

Final score = `sum(score * weight) / sum(weight)`. Threshold for pass = 3.5/5.

## Failure handling

- If a scenario errors (timeout, crash, malformed output), mark as ERROR not FAIL — these are infrastructure issues, not regressions.
- If the judge disagrees with itself between runs (variance check: run twice, take avg), log it and run a 3rd time to break the tie.
- If trigger accuracy drops below 80% on a target, halt the run and surface for human review — something fundamental broke.

## When to NOT run /eval

- Mid-development of a brand-new skill (run when stable, not before)
- During a high-cost session (each scenario is a `claude -p` call — count the tokens)
- When `~/.claude/evals/scenarios/<target>/` doesn't exist (tell the user to author scenarios first via `/eval-author <target>`)
