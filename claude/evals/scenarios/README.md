# Eval Scenarios

Each subdirectory is a target (skill, agent, or rule). Inside each target dir, each `.md` file is one scenario.

## Scenario file format

```markdown
---
name: scenario-short-name
description: One-line description of what this tests.
prompt: "The exact prompt to send to claude -p (single line, escaped)."
expects_skills:
  - skill-name           # skills that should be invoked via Skill tool
expects_tools:
  - Bash                 # tools that should appear in tool_use blocks
  - Edit
expects_agents:
  - verifier             # subagent_types that should be spawned
rubric:
  - criterion: "Calls the verifier agent before reporting task complete"
    weight: 3
  - criterion: "Output is under 200 words"
    weight: 1
  - criterion: "Includes file:line references for every claim"
    weight: 2
---

# Optional body — extra context for the judge, NOT sent to the model under test.

What good looks like:
- ...

What bad looks like:
- ...
```

## Targets to seed first

Every component we ship gets a starter scenario set:

| Target            | Min scenarios | Notes |
|-------------------|---------------|-------|
| `verifier`        | 5             | task complete with no tests, with passing tests, with failing tests, no Bash access, ambiguous |
| `team`            | 4             | trivial task (single agent), parallel-3, conflict resolution, mid-task failure |
| `mine-transcripts`| 3             | empty session, session with corrections, session with no learnings |
| `cache-report`    | 3             | first-run (cold), warm session, regressed session |
| `agent-tuner`     | 3             | clear failure pattern, ambiguous failure, false-positive |
| `spec-verifier`   | 4             | spec satisfied, spec missed, ambiguous spec, no spec exists |
| `CLAUDE.md`       | 6             | file-system-edit triggers /verify, plan mode triggers, hook precedence, etc. |

## Authoring discipline

- One scenario, one expectation. Don't bundle.
- Real prompts the user would actually type. Not synthetic test fixtures.
- Both happy path and failure modes. If you don't have a failure-mode scenario, you don't have an eval — you have a smoke test.
- Negative scenarios (skill should NOT activate) — at least 1 per target. False positives are as bad as false negatives.
