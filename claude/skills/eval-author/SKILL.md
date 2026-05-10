---
name: eval-author
description: Generate scenario stubs for /eval against a target agent or skill. Reads recent successful invocations from session transcripts and proposes 5+ scenarios covering happy path, edge cases, and negative cases. Triggers on /eval-author, "author scenarios for X", "create eval scenarios", "generate test cases for the X agent".
when_to_use: Before first /eval run on a target. After deploying a new agent or skill. When existing scenarios are stale.
allowed-tools: Read, Write, Glob, Grep, Bash
arguments: [target]
---

# /eval-author — Generate eval scenario stubs

`/eval-author <target>` produces 5+ starter scenario `.md` files at `~/.claude/evals/scenarios/<target>/`.

## What you do

### 1. Resolve target
- Skill (`~/.claude/skills/<name>/`) → scenarios test that the skill triggers correctly + produces useful output
- Agent (`~/.claude/agents/<name>.md`) → scenarios test the agent's protocol (happy + edge + adversarial)
- Rule (`~/.claude/rules/<name>.md` or CLAUDE.md) → scenarios test that Claude follows the rule

### 2. Read the target
Open the target's `.md` file. Extract:
- Description (what should trigger it)
- Protocol (what it does)
- Anti-patterns (what it should NOT do)
- Output format (what to validate)

### 3. Mine recent successful invocations
Find the last ~10 sessions where this target was used:
```bash
grep -l 'subagent_type":"<target>"' ~/.claude/projects/*/*.jsonl | head -10
# or for skills
grep -l '"skill":"<target>"' ~/.claude/projects/*/*.jsonl | head -10
```

For each, extract the user prompt that triggered it and a sketch of the expected output.

### 4. Generate scenarios

Author scenarios covering:
- **2 happy paths** — typical successful invocation
- **1 negative trigger** — a prompt that should NOT activate this target (test for false-positive triggering)
- **1 ambiguous case** — adversarial; expected result depends on judgment, document the expected behavior
- **1 edge case** — failure mode the protocol handles (or should)

### 5. Write each scenario

Format (frontmatter + optional body):

```markdown
---
name: <slug>
description: <one-line>
prompt: "<single-line user prompt>"
expects_skills:
  - <skill-name>     # if this scenario should activate a skill
expects_tools:
  - Bash             # tools that must appear
expects_agents:
  - <agent-name>     # subagent_types that should be spawned
rubric:
  - criterion: "<testable behavior>"
    weight: <1-3>
  - ...
---

## Why this scenario
<reason this case is worth testing>

## What good looks like
- <bullet>

## What bad looks like
- <bullet>
```

### 6. Verify
After writing all 5, run:
```bash
ls ~/.claude/evals/scenarios/<target>/
```

Show the user. They can run `/eval <target>` to execute them.

## Bootstrapping when no past invocations exist

If grep finds no prior invocations of the target (new agent/skill), author scenarios from the protocol description alone:
- Read each protocol step. Each has implicit success criteria → that's a rubric criterion.
- Each anti-pattern is a negative case to test.
- Description is the trigger phrase to validate.

## Anti-patterns

- Writing scenarios with vague rubric criteria ("works well")
- Copy-pasting the same prompt across scenarios (variety matters)
- Forgetting the negative trigger (false positives are as bad as false negatives)
- Authoring 20 scenarios — quality over quantity. 5 sharp scenarios beat 20 mush.
- Using prompts that wouldn't realistically be typed by a user
