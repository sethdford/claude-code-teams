---
name: verify
description: Prove that work actually behaves correctly by spawning the verifier agent to run the code and capture evidence. Use before claiming a task complete, before commit, when in doubt about whether tests prove the right thing. Triggers on /verify, "prove it works", "verify this", "did the change actually work".
when_to_use: Whenever you are about to assert a task is done, a fix is in, or a behavior holds. The verifier runs the code; you do not assert from reading.
allowed-tools: Agent, Read, Bash
arguments: [target]
---

# /verify — Prove behavior, don't infer it

`/verify [target]` spawns the **verifier** agent to actually execute the code and capture evidence.

## When to invoke

- About to mark a task complete
- About to commit
- After any non-trivial change
- When the user asks "does it work?" or "did that fix it?"
- After a Stop hook flagged unverified behavior

## What you do

1. **Identify the target.** If `target` is given, that's the change/area to verify. Otherwise, infer from recent context: the file you just edited, the task you just claimed done, the bug you just fixed.

2. **Compile the contract.** List 3–8 testable behaviors the change is supposed to satisfy. If you can't list them, the work isn't ready to verify — clarify the contract first.

3. **Spawn the verifier.** Use the `Agent` tool with `subagent_type: verifier`. Pass:
   - The target (files, commands, URLs)
   - The list of expected behaviors
   - Any known test commands (`pnpm test`, `pytest path/to/file.py`, `curl ...`)
   - Any constraints (don't hit prod, run only local)

4. **Read the verifier's output.** It will end with one of:
   - `RESULT_verifier=PASS` — proceed with whatever you were about to do
   - `RESULT_verifier=FAIL` — STOP. Surface the failed behaviors. Do not claim done.
   - `RESULT_verifier=INCONCLUSIVE` — STOP. Surface the blocker. Verification couldn't complete.

5. **Never override.** If the verifier says FAIL or INCONCLUSIVE, you do not say "I think it's fine anyway." You either fix the issue or surface it to the user.

## Anti-patterns to refuse

- Calling /verify without a clear contract — don't ask the verifier to prove "this works" with no specifics.
- Calling /verify and then ignoring the result.
- Spawning the verifier and then doing the verification yourself in parallel.

## Composition with other skills

- After `/eval`: run /verify on any newly-built skill before promoting it
- Before `commit-commands:commit`: /verify the change first
- Inside `/team`: every agent's task closure runs /verify before TaskUpdate marks it done
