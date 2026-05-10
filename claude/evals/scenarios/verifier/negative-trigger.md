---
name: negative-trigger
description: A prompt that should NOT activate the verifier. Catches false-positive activation.
prompt: "Write me a verifier function in Python that checks if a string is a valid email address."
rubric:
  - criterion: "Does NOT spawn the verifier subagent (this is a Python coding request, not a verification task)"
    weight: 4
  - criterion: "Implements an email-validating function in plain Python"
    weight: 2
  - criterion: "Does NOT emit RESULT_verifier=anything (it's not a verification run)"
    weight: 3
---

## Why this matters
The word "verifier" appearing in a prompt does not mean we want the verifier agent. The user wants Python code that verifies emails. False positive activation costs tokens and confuses the user.

A correct response writes the Python function directly, optionally pointing out that for verifying our project's verifier agent, the user would say "verify X" or "/verify".
