---
name: tune-agent
description: Propose a Reflexion-style patch to a specific agent's prompt based on evidence of recurring failures. Use when the same agent makes the same class of mistake twice, when /mine-transcripts surfaces an agent in agent-tuning.md, or when /eval flags a regression on an agent. Triggers on /tune-agent, "tune the X agent", "fix the agent prompt".
when_to_use: Only after ≥2 pieces of evidence of the same failure class. Not for one-off mistakes — those are noise.
allowed-tools: Agent, Read, Bash, Edit, Write, Glob, Grep
arguments: [agent-name]
---

# /tune-agent — Reflexion patch for an agent's prompt

`/tune-agent <name>` spawns the `agent-tuner` agent with collected evidence and proposes a focused patch to that agent's `.md` file.

## When to invoke

- `/mine-transcripts` produced `agent-tuning.md` listing agents with ≥2 failures
- `/eval` shows a regression for a specific agent vs prior runs
- Verifier or critic flagged the same failure pattern from the same agent twice in this session
- The user says "this agent keeps doing X — fix it"

## What you do

1. **Resolve the agent.** `~/.claude/agents/<name>.md` must exist. If not, stop.

2. **Collect evidence.** Pull from:
   - Most recent `~/.claude/telemetry/mining-runs/*/agent-tuning.md` (if applicable)
   - Verifier/critic outputs in this session that mention the agent
   - Any context the user just provided
   
   Need ≥2 pieces. If you have only 1, tell the user — wait for more before tuning.

3. **Spawn agent-tuner.** Use the `Agent` tool with `subagent_type: agent-tuner`. Pass the evidence as a structured prompt:
   ```
   Agent to tune: <name>
   Evidence:
   1. <task summary> — <what went wrong> — session=<id>
   2. <task summary> — <what went wrong> — session=<id>
   3. <task summary> — <what went wrong> — session=<id>
   
   Desired behavior: <if user specified, otherwise infer>
   ```

4. **Read the tuner's output.** It ends with one of:
   - `RESULT_agent-tuner=PATCHED` — surface the diff and rationale to the user; ask "apply or revert?"
   - `RESULT_agent-tuner=INSUFFICIENT_EVIDENCE` — tell user, suggest waiting
   - `RESULT_agent-tuner=AMBIGUOUS` — surface options to user
   - `RESULT_agent-tuner=NO_PATCH_NEEDED` — evidence didn't add up; explain

5. **Apply or revert.**
   - On user approval: leave the change in place (the tuner already wrote it).
   - On rejection: `cp ~/.claude/agents/.history/<name>-<ISO>.md ~/.claude/agents/<name>.md` to restore.
   - Either way, log to `~/.claude/agents/.history/CHANGELOG.md` (the tuner already did this).

6. **Re-eval.** After applying, run `/eval <name>` to confirm the patch doesn't regress other behaviors.

## Cost note

The tuner runs on Opus (precise prompt engineering matters). One invocation is typically <$0.50. If you find yourself tuning the same agent more than weekly, the agent's design is wrong — propose a redesign, not another patch.

## Anti-patterns to refuse

- Tuning on a single occurrence (refuse — collect more evidence first)
- Tuning based on user vibes rather than logged failures
- Tuning multiple agents in one shot — each `/tune-agent` is one agent
- Skipping the post-patch `/eval` — you must verify the patch doesn't regress
