---
name: spec
description: Author a three-file spec (requirements / design / tasks) before non-trivial implementation, then verify the implementation satisfies the spec. Adopts the Kiro spec-driven development pattern. Use for features that span 3+ files, new public APIs, or anything you'd want a human to design-review. Triggers on /spec, "write a spec", "spec this out", "design before build".
when_to_use: Before implementation of any non-trivial feature. After /verify catches a gap between intent and behavior. When the user asks for a design before code.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
arguments: [feature-name]
---

# /spec — Three-File Spec Workflow

`/spec <feature-name>` walks through requirements → design → tasks, then sets up the verification gate.

## The three files

All under `<project>/specs/<feature-name>/`:

| File | Purpose | Lifecycle |
|---|---|---|
| `requirements.md` | User stories + acceptance criteria | Written first, treated as the contract |
| `design.md` | Architecture: components, data flow, decision rationale | Written after reqs, before tasks |
| `tasks.md` | Numbered list of implementable units, each maps to ≥1 acceptance criterion | Written last, drives execution |

## The flow

### 1. requirements.md
Format:
```markdown
# <feature> — Requirements

## User stories
- As a <role>, I want to <action>, so that <outcome>.
- ...

## Acceptance criteria
- [ ] AC-1: <testable behavior>
- [ ] AC-2: <testable behavior>
- ...

## Non-goals
- <what this feature does NOT do, to prevent scope creep>

## Constraints
- <perf budget, deps allowed/disallowed, compat surface, etc.>
```

Each AC must be one sentence and testable. "Robust error handling" is not an AC. "Returns 400 with `{error: ...}` for malformed JSON" is.

### 2. design.md
Format:
```markdown
# <feature> — Design

## Components
- <name>: <what it does> — <where it lives>
- ...

## Data flow
1. <step>
2. ...

## Decisions
- **<decision>**: chose <option A> over <option B> because <reason>
- ...

## Risks
- <thing that could go wrong> — <mitigation>
```

Each Decision must reference one or more ACs it serves. If a decision doesn't tie to an AC, either the AC is missing or the decision is unjustified.

### 3. tasks.md
Format:
```markdown
# <feature> — Tasks

| # | Task | ACs | Owner | Status |
|---|---|---|---|---|
| 1 | <imperative description> | AC-1, AC-2 | <agent or person> | pending |
| ... |

## Dependencies
- Task N depends on Task M
- ...
```

Each task maps to ≥1 AC. Each AC is covered by ≥1 task. If you can't make this map, the spec is incomplete.

## Your protocol

### Phase 1 — Requirements (with user)
1. Distill the user's stated goal into 3–8 acceptance criteria.
2. List the obvious non-goals (things you'd be tempted to add but shouldn't).
3. Surface constraints the user implied (perf, security, compat).
4. Show requirements.md to user for approval. Do not proceed without it.

### Phase 2 — Design
1. Write design.md based on the approved requirements + your read of the codebase.
2. Use Plan Mode (Shift+Tab×2) before writing the design — let it spawn parallel subagents to explore relevant files.
3. Every Decision tags ≥1 AC.
4. Show design.md to user for approval before tasks.

### Phase 3 — Tasks
1. Decompose into independently verifiable units.
2. Each task: imperative description, ACs covered, dependencies, owner.
3. Tag tasks for `/team` if multi-agent dispatch makes sense.

### Phase 4 — Hand off
- If the user wants to implement now: kick off `/team` with the tasks list, OR proceed sequentially yourself.
- The `spec-verifier` agent will be spawned by the Stop hook to confirm impl satisfies spec before session close.

## Verification at completion

Once implementation is done, spawn `spec-verifier`:
```
Agent({
  description: "Verify spec satisfaction",
  subagent_type: "spec-verifier",
  prompt: "Spec at <path>. Impl at <files>. For each AC: does the implementation prove it? Output RESULT_spec-verifier=..."
})
```

If `RESULT_spec-verifier=FAIL` for any AC, the work isn't done — surface gaps, file new tasks.

## When NOT to use /spec

- Single-file fixes — overhead exceeds value
- Refactors with no behavior change — use `/team` directly
- Exploratory spikes — write a throwaway, commit nothing, spec the keeper afterwards

## Anti-patterns to refuse

- Writing all three files in one shot without user review between phases
- Writing a design before requirements are signed off
- Tasks that don't map to ACs (these are wishful work)
- ACs that aren't testable ("works well", "is performant", "is intuitive")
