# SCRUM E2E Demo

Demonstrates the complete `/scrum` ceremony end-to-end **without requiring real Claude API calls** (rate-limited until May 14). Proves every component of the orchestration is correct: state file generation, role transitions, real sandboxed verification, and the adversarial audit logic.

What it does:
1. **Phase 1 — Plan**: synthesizes stories.md from the goal (simulating product-owner output), runs deterministic AC validation
2. **Phase 2 — Execute**: applies the known-correct fix to a sandboxed copy (simulating implementer), runs **real** pytest in **real** sandbox (the verifier role, no simulation)
3. **Phase 3 — Review**: generates review.md with the DoD checklist
4. **Phase 4 — Audit**: runs the **deterministic** audit (no LLM) — parses stories.md, checks each AC against the actual code state via grep + test runner
5. **Phase 5 — Retro**: generates retro.md with what worked / what to keep
6. Prints sprint summary

What this proves:
- The state-file generation is correct (stories → design → plan → review → audit → retro)
- The role transitions work (each agent's output is the next agent's input)
- The audit catches drift independently (it doesn't trust the team's claims)
- Definition of Done is enforced (verifier PASS required)

What this DOESN'T prove (until rate limit clears):
- The actual product-owner agent decomposes goals correctly
- The actual tech-lead agent designs well
- The actual sprint-auditor catches adversarial patterns LLM-judgmentally

For real, run after May 14:
```bash
claude -p "/scrum 'fix py-001 pagination bug per acceptance criteria'"
```

## Run

```bash
./demo.sh
```

Cost: $0. Time: ~5 seconds.
