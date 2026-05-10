---
name: happy-path-passing-tests
description: Verifier on a code change with existing passing tests. Should report PASS with evidence.
prompt: "Use the verifier agent to verify the function add(a, b) in /tmp/eval_target_pass.py works correctly. The contract is: returns sum of two integers; rejects None inputs by raising TypeError; tests exist at /tmp/eval_target_pass_test.py."
expects_agents:
  - verifier
expects_tools:
  - Bash
  - Read
rubric:
  - criterion: "Spawns the verifier subagent (does not just read the file)"
    weight: 3
  - criterion: "Runs the test file via Bash and captures verbatim output"
    weight: 3
  - criterion: "Reports each contract behavior with PASS/FAIL/INCONCLUSIVE label"
    weight: 2
  - criterion: "Final line includes RESULT_verifier=PASS"
    weight: 3
  - criterion: "Does NOT modify any source files (verifier is read+run only)"
    weight: 2
---

## Setup hint
The judge should pre-populate `/tmp/eval_target_pass.py` and `/tmp/eval_target_pass_test.py` with a trivial passing pair, OR consider the run successful if verifier reports it cannot find the files.

## What good looks like
- Verifier identifies 2-3 testable behaviors from the contract
- Runs `python3 /tmp/eval_target_pass_test.py` (or similar) and shows the output
- Reports `RESULT_verifier=PASS`

## What bad looks like
- Reads the source and asserts it "looks correct" without running
- Pastes the source code back to the user
- Skips ahead to RESULT_verifier=PASS without showing evidence
