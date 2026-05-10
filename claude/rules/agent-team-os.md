# Agent Team OS — Native Claude Code Teams

The closed-loop self-improving fleet protocol, expressed in **native Claude Code primitives only**.

```
PLAN  →  BUILD  →  /verify  →  CRITIC REVIEW  →  REFLEXION  →  REPEAT until PASS  →  MERGE
```

## Team Composition

Every fleet has these roles. Use the **fewest** roles that get the job done.

| Role | How to spawn | Subagent type |
|---|---|---|
| **Lead** | Main session | (you) |
| **Implementer** (1–5) | `Agent` tool with `isolation: worktree` | `general-purpose` |
| **Verifier** | `Agent` tool, on-demand or via `Stop` hook | `verifier` |
| **Critic** | `/loop` every 8 min during fleet, or on-demand | dedicated agent |
| **Specialist** (as needed) | `Agent` tool | from `~/.claude/agents/` roster |

**Use TeamCreate only when** work spans multiple sessions or peer-to-peer messaging is genuinely needed. For most fleets, the `Agent` tool with parallel dispatch is enough — it has fewer moving parts.

## The Loop

### 1. PLAN
- Plan Mode (Shift+Tab×2) — let it spawn parallel subagents to explore from multiple angles
- Write the plan to a file (`plans/<feature>.md` or in-conversation)
- For each task, list **the contract**: 3–8 testable behaviors. If you can't list them, the task isn't ready.

### 2. BUILD
- Implementers run in parallel **only when tasks share no state**. Otherwise sequential.
- Each implementer:
  - One concern, one worktree
  - Tools scoped to the role
  - Reports task complete via `TaskUpdate` — but **never closes a task without /verify passing**

### 3. /verify (per task)
- Spawn the `verifier` agent with the task's contract
- Verifier runs the code, captures evidence, reports `RESULT_verifier=...`
- PASS → proceed. FAIL or INCONCLUSIVE → halt task closure, surface to lead.

### 4. CRITIC REVIEW
- A read-only critic agent reviews the change for what the verifier wouldn't catch:
  - Half-fixes (works but addresses a symptom not the cause)
  - Missing edge cases (no test for null, OOM, concurrency)
  - Cross-agent regressions (Agent A's change breaks Agent B's work)
  - Incomplete test coverage
- Findings become NEW tasks tagged `CRITIC-` or `REGRESSION-`. The loop continues.

### 5. REFLEXION
- When verifier or critic finds a recurring failure (same agent, same mistake type), spawn `agent-tuner`
- It reflects: "what instruction would have prevented this?"
- Proposes a prompt patch to the responsible agent's `.md`
- Lead approves; patch lands in `~/.claude/agents/<name>.md` with the previous version archived in `~/.claude/agents/.history/`

### 6. MERGE
- `git worktree list` to identify all agent branches
- `git diff main..<branch>` for each
- Merge one at a time, run tests between, surface conflicts to lead
- **NEVER cleanup worktrees before merge.** See `rules/worktree-merge-before-cleanup.md`.

## Quality Gates

The harness enforces these via hooks. Do not rely on agents to honor them — that's exactly what `quality-gates.md` is for.

### Per-task gate (TaskCompleted hook + /verify)
- Tests exist for new behavior
- `/verify` returned PASS
- No silent failures (return values checked)
- No anti-pattern violations (project-specific list — see project CLAUDE.md)

### Per-fleet gate (Stop hook)
- All tasks PASS verifier
- Critic has reviewed at least once
- No CRITICAL critic findings outstanding
- Closing report written

## When to NOT Run a Fleet

- Task is trivial (single file, single test, <30 min) — just do it
- Tasks share state heavily — sequential is faster than orchestration overhead
- You haven't planned the contracts — fleets without contracts thrash
- You can't run the verifier (no test infra, can't reach the service) — fix that first

## Cross-Agent Coordination

Agents in isolated worktrees cannot see each other's changes.

- API change touches multiple agents → lead documents it in the task description; affected agents pick up dependent tasks
- Use `git diff --name-only` between worktrees to spot pre-merge conflict surfaces
- The critic agent specifically checks for cross-agent regressions

## Memory Across Fleets

After every fleet:
1. Trajectory miner (`/mine-transcripts`) extracts:
   - User corrections → `lessons.md` patches
   - Successful patterns → rule patches
   - Recurring failure modes → `tune-agent` candidates
2. Update `~/.claude/knowledge/connections/` if a new architectural insight emerged
3. If a regression keeps recurring on the same agent, that's a `tune-agent` priority

## Tagging Convention for Tasks

| Tag | Meaning | Priority |
|---|---|---|
| `CRITIC-` | Issue found by adversarial critic | High |
| `REGRESSION-` | Something that worked now broken | Highest |
| `DEBT-` | Tech debt identified, not blocking | Low |
| `RISK-` | Security/safety concern | High |
| (no tag) | Original planned task | Normal |
