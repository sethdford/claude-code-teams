---
name: team
description: Spin up a native Claude Code Teams fleet to tackle a multi-step task — lead orchestrates, specialists work in parallel worktrees, critic + verifier loop guards quality. Use when the task has 3+ independent sub-tasks, when you need different specialists, or when isolation between concerns is required. Triggers on /team, "spin up a team", "fan out", "fleet this".
when_to_use: Use for tasks with 3+ independent units of work that benefit from specialization. Do NOT use for trivial single-file fixes or tasks with heavy shared state — sequential is faster.
allowed-tools: Agent, Task, TodoWrite, Bash, Read, Write, Edit, Glob, Grep, Skill
arguments: [goal]
---

# /team — Native Claude Code Teams Orchestrator

`/team <goal>` runs the closed-loop multi-agent protocol from `~/.claude/rules/agent-team-os.md` end-to-end with native primitives. Replaces Shipwright; depends only on the Claude Code harness.

## The protocol you run

```
1. SCOPE     — distill goal into 3–8 testable contracts (with user)
2. PLAN      — write the plan; identify which contracts are independent (parallel) vs sequential
3. SPAWN     — Agent tool with isolation: worktree, model: sonnet, tools scoped to role
4. WATCH     — TodoWrite tracks tasks; agents report back via TaskUpdate
5. VERIFY    — for each task close, spawn verifier (model: sonnet)
6. CRITIQUE  — every N completions, spawn critic to find half-fixes & cross-agent regressions
7. REFLEX    — recurring failures from same agent → spawn agent-tuner with /tune-agent
8. MERGE     — git diff each worktree, merge sequentially with tests between, surface conflicts
9. CLOSE     — write closing report + update knowledge + run /mine-transcripts on this session
```

## Hard rules

- **Never** call `TeamDelete`, `git worktree remove`, or `ExitWorktree` until **after** all branches are merged. See `rules/worktree-merge-before-cleanup.md`.
- **Never** mark a task complete without `RESULT_verifier=PASS`.
- **Never** skip the critic on the closure of CRITICAL or REGRESSION-tagged tasks.
- **Always** keep the active task list in `TodoWrite` — every spawn updates it.
- **Always** report cost+token totals in the closing summary. If the run cost >$10, flag it.

## Step-by-step

### Step 1 — Scope (with user)
- Distill the goal into 3–8 testable contracts. Each contract is one sentence: "X must do Y when Z."
- If you can't list ≥3 contracts, the goal is too small for /team — just do it.
- Confirm with the user before spawning anyone.

### Step 2 — Plan
- Group contracts into independent vs sequential clusters.
- For each cluster, decide: which specialist(s) handle this?
  - General task → `general-purpose`
  - Migration → `migration-planner`
  - Bug regression → `regression-hunter`
  - Perf → `latency-profiler`
  - Security → `security-reviewer`
  - (See `~/.claude/agents/` for the full roster — match agent description to task.)
- Write the plan inline in this conversation. Don't burn context with a separate plan file unless the user wants one.

### Step 3 — Spawn
For each independent unit:

```
Agent({
  description: "<short description>",
  subagent_type: "general-purpose",  // or specialist
  isolation: "worktree",             // ALWAYS for implementation tasks
  prompt: "..."                       // include: contract, file paths, no-go zones, when to /verify
})
```

For parallel dispatch: emit multiple `Agent` calls in a SINGLE message. Don't sequentially await unless there's a real dependency.

### Step 4 — Watch
- `TodoWrite` immediately after spawn: each task in_progress
- When an agent reports back, mark its task completed (after verify passes)
- If the user asks for a status, just `TodoWrite` view + a 2-line summary

### Step 5 — Verify (per task close)
- Spawn `/verify` (which spawns the `verifier` agent)
- Read `RESULT_verifier=...`
- PASS → `TodoWrite` mark complete
- FAIL → keep task open, surface the failure, prompt the responsible agent to fix
- INCONCLUSIVE → escalate to user; do not silently pass

### Step 6 — Critique (every 3 completions, or at fleet end)
- Spawn the `critic` agent (read-only) with the list of just-completed tasks
- Critic returns CRITICAL / HIGH / MED findings; CRITICAL ones become new tasks (CRITIC- prefix)
- Critic also checks for cross-agent regressions: did Agent A's change break Agent B's work?

### Step 7 — Reflexion (only if pattern emerges)
- If verifier or critic finds the SAME failure mode from the SAME agent twice, that's a tuning candidate
- Spawn `/tune-agent <agent-name>` with the failure evidence
- It proposes a prompt patch; you (lead) approve or reject
- Approved patches land in the agent's `.md` with backup at `~/.claude/agents/.history/`

### Step 8 — Merge
- `git worktree list` shows all branches
- For each: `git diff <main>..<branch>`, then merge
- After every merge, run the project's test suite — surface failures immediately
- DO NOT remove worktrees until all merges complete

### Step 9 — Close
- Write a closing report to the conversation:
  - Goal recap, contracts satisfied (link to evidence)
  - Tasks: completed / deferred (with reason)
  - Critic findings: addressed / accepted as known issues
  - Cost / tokens / wall time
  - Lessons learned (auto-extracted from this session)
- Run `/mine-transcripts --since 1h` to capture this fleet's lessons
- Update `~/.claude/knowledge/connections/` if a new architectural insight emerged

## Output discipline

- Status updates: 2 lines max per teammate update — don't paste their work back to the user
- Use `TodoWrite` as the source of truth, not chat narration
- Closing report under 500 words

## Common failure modes you must avoid

1. **Spawning a fleet for a 1-hour task** — overhead exceeds value
2. **Spawning agents without contracts** — they thrash because they can't tell when they're done
3. **Skipping verifier because "it obviously works"** — that exact phrase has cost users tens of hours
4. **Removing worktrees before merge** — destroys all the agent's work
5. **Critic running on unrelated work** — scope the critic to just-closed tasks
6. **Letting the critic loop run forever** — cap at 3 critic passes; remaining findings become explicit deferred tasks
