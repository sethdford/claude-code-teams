# Global Operating Instructions

> Lean by design. If a rule isn't pulling its weight, delete it.

## The Five Operating Principles

1. **Plan before you build.** Shift+Tab twice for any non-trivial task. Plan mode now spawns parallel subagents to explore the codebase from multiple angles before producing a plan — use it.

2. **Hooks are guarantees, CLAUDE.md is suggestions.** When you find yourself adding a "from now on, always do X" rule here, ask first: should this be a hook? Determinism belongs in the harness, not the prompt.

3. **Verify, don't assert.** Never say "the fix is in" or "tests pass" without spawning the `verifier` agent (`/verify`) to actually run the code and capture evidence. Reading code is not verification.

4. **Measure before tuning.** Don't add rules without an eval scenario in `~/.claude/evals/scenarios/`. Don't change rules without re-running `/eval`. The eval harness exists; use it.

5. **Skills, agents, hooks — one job each.** A skill that does five things triggers wrong. An agent that handles five domains drifts. A hook that fires on five matchers becomes its own bug source.

## Native Claude Code Teams

Multi-agent work uses native primitives only. No external orchestrator.

| Primitive | Use for |
|---|---|
| `Agent` tool with `subagent_type` + `isolation: worktree` | Specialist worker doing a focused task in an isolated worktree |
| `TeamCreate` + `TaskCreate` + `TaskUpdate` | Sustained multi-session collaboration with a shared task list |
| Skill `context: fork` | One-off skill execution in a fresh context window |
| `/loop` + scheduled tasks | Recurring background work (critic, verifier, miner) |

Decision rule from production playbooks: **multi-agent only when phases are genuinely asynchronous or involve different specialists.** A well-decomposed single agent beats a multi-agent setup most of the time.

When you do fan out:
- One concern per agent. If the description has "and", split it.
- Tools scoped to the role. Read-heavy planners get search/docs. Implementers get Edit/Write/Bash.
- Worktree isolation for any agent that edits files.
- **Merge before cleanup.** Always. See `rules/worktree-merge-before-cleanup.md`.

## The Loop You Always Run

```
PLAN  →  BUILD  →  /verify  →  CRITIC REVIEW  →  REFLEXION  →  REPEAT
                       ↑
                       evidence, not opinion
```

- **PLAN**: Plan Mode (Shift+Tab×2) for anything non-trivial. Output: a written plan, a list of contracts to verify.
- **BUILD**: implementation. Edit/Write/Bash. Don't claim done.
- **/verify**: spawn the `verifier` agent. It runs the code and reports `RESULT_verifier=PASS|FAIL|INCONCLUSIVE`. If anything other than PASS, you are not done.
- **CRITIC REVIEW**: a separate agent reviews quality, edge cases, and cross-agent regressions. Findings become new tasks.
- **REFLEXION**: failures from verifier or critic feed `agent-tuner`, which proposes prompt patches to the responsible agent. You approve. The patch lands in `~/.claude/agents/.history/`.

## Built-In Skills

| Skill | Use for |
|---|---|
| `/eval` | Test that a skill/agent triggers correctly + measure output quality vs rubric |
| `/verify` | Spawn the verifier agent to prove behavior |
| `/cache-report` | Cache hit-rate health check + anomaly detection |
| `/team` | Spin up a native Claude Code Teams fleet with critic+verifier loop |
| `/spec` | Three-file spec (requirements/design/tasks) before non-trivial implementation |
| `/mine-transcripts` | Trajectory miner — turns past sessions into rule/lesson PRs |
| `/tune-agent` | Reflexion patch proposal for an agent's prompt |
| `/best-of-n` | Test-time scaling — N rollouts + critic ranking + USC + confidence weighting |
| `/aspect-panel` | 5-aspect verifier panel (correctness, edge-case, security, regression, style) |
| `/ab-test` | A/B test agent prompt variants |
| `/rl-status` | Per-agent reward + value snapshot |
| `/eval-author` | Generate scenario stubs |
| `/apply-mining-patches` | Apply approved trajectory diffs |

## Memory Discipline

- **CLAUDE.md** (this file): rules and principles. Concise. Goal: under 200 lines.
- **`~/.claude/rules/*.md`**: modular rules loaded automatically. One topic per file.
- **`~/.claude/knowledge/`**: structured durable knowledge (concepts, connections, qa) — populated by `/mine-transcripts`.
- **`~/.claude/lessons.md`**: failure patterns and corrections. Use Zep-style `valid_from`/`superseded_by` (mark, don't delete).
- **`~/.claude/projects/<dir>/memory/`**: per-project auto-memory.

## Token Discipline

Hit-rate target: **≥85%**. Below 70% triggers an anomaly entry; investigate via `/cache-report`.

- `.claudeignore` in every project
- Plan Mode for analysis-heavy work (cuts tokens 40–50%)
- Subagents for data-heavy ops (only the summary returns to your context)
- `--bare` mode for headless eval/CI runs
- `CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE=70`
- Don't push past 80% context — break work, don't pile

## Tool Choice

| Want | Use |
|---|---|
| Read a file | `Read` (not `cat`) |
| Find files | `Glob` (not `find`) |
| Search content | `Grep` (uses ripgrep — never plain `grep`) |
| Edit a file | `Edit` (not `sed`) |
| Run code | `Bash` |
| Spawn helper | `Agent` (read-only research → Explore subagent; building → general-purpose; isolated → +worktree) |
| Recurring | `/loop` for in-session, `schedule` for cross-session |
| Long-running | `Bash` with `run_in_background: true` |

## Failure Recovery

- **Tests fail**: read full output, fix code (not test), re-run specific test, then full suite.
- **Merge conflict**: never `--force`, never discard work. Read both versions. Run tests after resolution.
- **Context tight**: `/context` to inspect, summarize completed work to memory, break next steps into smaller tasks.
- **Verifier says FAIL**: do not override. Fix the issue or surface to user.
- **Cache hit rate dropped**: `/cache-report`, identify what changed, audit recent CLAUDE.md/rules edits.

## What This File Does NOT Cover

- **Project-specific conventions** → that project's own `CLAUDE.md` and `.claude/rules/`
- **Language-specific patterns** → project-level
- **Toolchain quirks** → project-level
- **Per-domain expertise** → skills (`.claude/skills/`) and specialist agents (`.claude/agents/`)

If you find yourself reaching for a project-specific rule from this file, that rule is misplaced. Move it.

## Self-Improvement

After any user correction:
1. Fix the immediate issue.
2. Decide: is this a one-off, a CLAUDE.md rule, a hook, or a skill?
   - One-off → move on
   - Pattern that recurs in many projects → CLAUDE.md or rule
   - Determinism that should be enforced → hook
   - Repeatable workflow → skill
3. Append to `~/.claude/lessons.md` with `Why:` and `How to apply:` lines.
4. If it's a hook-shaped rule, propose the hook explicitly — don't just stash it as an instruction.

The trajectory miner (`/mine-transcripts`) automates step 3 from session transcripts. Run it weekly.
