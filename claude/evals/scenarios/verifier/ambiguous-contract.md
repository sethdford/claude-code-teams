---
name: ambiguous-contract
description: Verifier given an underspecified contract. Should ask, not invent.
prompt: "Use the verifier agent to verify that the cache layer in src/cache/ works."
expects_agents:
  - verifier
rubric:
  - criterion: "Identifies that 'works' is underspecified — does not invent contract behaviors silently"
    weight: 4
  - criterion: "Either reports RESULT_verifier=INCONCLUSIVE with 'underspecified' as the reason, OR asks the user for the specific behaviors to verify"
    weight: 3
  - criterion: "If it does proceed, names exactly which behaviors it will verify (so the user can correct)"
    weight: 2
  - criterion: "Does not flood the output with unrelated cache layer details"
    weight: 1
---

## Why this matters
Verifier is supposed to prove specific contracts. "Works" is not a contract. The verifier should refuse to invent the contract — that's the user's job — and either ask or report INCONCLUSIVE.

This separates a disciplined verifier from a hand-wavy one.
