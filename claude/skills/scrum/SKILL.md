---
name: scrum
description: Run a complete SCRUM sprint with all ceremonies — Product Owner authors stories, Tech Lead designs, Scrum Master orchestrates implementers, Verifier+Aspect-Panel guard quality, Sprint Auditor adversarially audits, Retro feeds back to /tune-agent. Triggers on /scrum, "run a sprint", "scrum me this", "ship this with full process".
when_to_use: Multi-story bodies of work where you want the full SDLC ceremony — backlog discipline, design review, parallel implementation, quality gates, audit, retro. NOT for single-line fixes (overkill). NOT for exploratory spikes (use /spec instead).
allowed-tools: Agent, Task, TodoWrite, Bash, Read, Write, Edit, Glob, Grep, Skill
arguments: [goal]
---

# /scrum — Full SDLC sprint with adversarial audit

`/scrum "<goal>"` orchestrates a complete SCRUM team to deliver a multi-story sprint.

## The ceremonies

```
1. SPRINT PLANNING
   product-owner    → backlog of user stories + AC
   tech-lead        → design + risk + sequencing for each story
   scrum-master     → wave plan + agent assignments

2. WAVE EXECUTION (per parallel cluster)
   implementer agents (general-purpose / specialists, isolation: worktree)
     → work
   verifier         → runs code, captures evidence, RESULT_verifier=PASS
   aspect-panel     → confidence-weighted vote across 5 specialized verifiers
   critic           → adversarial code review

3. SPRINT REVIEW
   scrum-master     → DoD checklist per story; only closes on full evidence

4. SPRINT AUDIT (adversarial)
   sprint-auditor   → independently re-derives whether each AC was delivered
                      adversarial: looks for drift, scope creep, mocked tests,
                      DoD violations, narrow fixes, dropped ACs

5. RETROSPECTIVE
   /mine-transcripts → extract corrections + patterns from sprint
   /tune-agent       → if any agent had ≥2 verifier failures, propose patch
   retro.md          → what worked, what broke, what to change next sprint
```

## Files written per sprint

```
<project>/sprints/sprint-<N>/
├── stories.md       (product-owner)
├── designs/<US>.md  (tech-lead, one per story)
├── plan.md          (scrum-master)
├── evidence/<US>/   (verifier + panel + critic outputs per story)
├── review.md        (scrum-master)
├── audit.md         (sprint-auditor)
└── retro.md         (final)
```

## Your protocol

### Phase 1: Plan
1. Spawn `product-owner` agent with the goal. It returns `RESULT_product-owner=READY|NEEDS_CLARIFICATION|NEEDS_DESCOPE`.
   - If NEEDS_CLARIFICATION: surface to user, wait, retry.
   - If NEEDS_DESCOPE: split goal across multiple sprints; user picks first.
2. For each story (parallel where possible), spawn `tech-lead` to author design + risk.
3. Spawn `scrum-master` with the stories + designs to write the wave plan.

### Phase 2: Execute
For each wave in plan:
1. Read scrum-master's plan; identify the agents to spawn.
2. Spawn parallel implementer agents (`Agent` tool with `isolation: worktree`).
3. After each implementer reports done:
   - Spawn `/verify` for that story (verifier agent runs the code)
   - If verifier PASS: spawn `/aspect-panel` for orthogonal coverage
   - If panel returns ESCALATE: surface to user; do not auto-resolve
   - Mark story DONE in TodoWrite **only** when both PASS

### Phase 3: Review
Spawn `scrum-master` Phase 5 (Sprint Review). It writes review.md with the DoD checklist per story.

### Phase 4: Audit (mandatory — never skip)
Spawn `sprint-auditor` with paths to stories.md and review.md. It returns one of:
- `RESULT_sprint-auditor=PASS` → sprint closes
- `RESULT_sprint-auditor=PASS_WITH_NOTES` → sprint closes; notes go to retro
- `RESULT_sprint-auditor=FAIL` → DO NOT CLOSE. Re-open the failing stories. Re-execute.
- `RESULT_sprint-auditor=INCONCLUSIVE` → surface to user; ask for missing access

### Phase 5: Retro
1. Run `/mine-transcripts --since <sprint-start>` over this sprint's session window.
2. Read agent-tuning candidates. If any agent appears ≥2 times: recommend `/tune-agent <name>`.
3. Write retro.md with: what worked, what broke, what changed next sprint, any tuning candidates.

### Phase 6: Close
Mark all sprint TodoWrite items completed. Print summary to user.

## Hard rules

- **No story closes without verifier PASS + panel PASS/CLEAN.** Hold the line even when implementer is confident.
- **Audit is mandatory.** Never skip Phase 4.
- **Audit FAIL re-opens stories.** Don't quietly accept partial deliveries.
- **No scope creep without explicit PO sign-off.** sprint-auditor catches this; respect it.
- **Retro happens even on perfect sprints.** Even green-on-everything has lessons.

## Cost discipline

A typical 3-story sprint costs:
- product-owner: ~$0.30 (Sonnet, 1 invocation)
- tech-lead: 3 × ~$0.50 (Opus, 1 per story)
- implementer: 3 × ~$1.00-2.00 (sonnet/opus, varies)
- verifier: 3 × ~$0.20
- aspect-panel: 3 × ~$0.50 (5 verifiers each, sonnet)
- critic: 3 × ~$0.20
- sprint-auditor: 1 × ~$0.80 (Opus, careful read)
- mine-transcripts retro: ~$0.50

Total per sprint: ~$8-15. Verify against `--max-budget-usd 20` per sprint by default.

## When NOT to use /scrum

- Single-line fix (just edit it; the ceremony costs more than the work)
- Exploratory spike (use `/spec` for design-first; use plain `/team` for implementation if it pans out)
- No clear acceptance criteria possible (PO will refuse; surface to user first)
- Test infrastructure missing (verifier can't run; auditor will be INCONCLUSIVE)

## Anti-patterns to refuse

- Closing a sprint without sprint-auditor running
- Treating audit FAIL as advisory (it is HARD)
- Skipping retro
- Letting the scrum-master write code (orchestration only)
- Letting sprint-auditor trust the team's claims (independent verification only)
- Running stories sequentially when they're independent (use waves)
- Running stories in parallel when they share state (don't)

## Last line

When the sprint closes successfully:
```
RESULT_scrum=SPRINT_CLOSED N=<sprint-num> stories=<n>/<m> audit=PASS retro=<path>
```

When the sprint cannot close:
```
RESULT_scrum=BLOCKED reason=<audit-fail|inconclusive|user-input-needed>
```
