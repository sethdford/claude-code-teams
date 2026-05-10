# Quality Gates — Universal Enforcement Checklist

Language-agnostic. Per-language and per-project anti-patterns belong in that project's CLAUDE.md, not here.

## Per-Task Gate (before TaskUpdate marks complete)

### Behavior verification
- [ ] `/verify` ran and returned `RESULT_verifier=PASS`
- [ ] Tests exist for new functionality (happy path AND error paths)
- [ ] Edge cases tested where they exist (NULL/empty/overflow/concurrent — pick the ones that apply)
- [ ] No silent failures: return values checked, errors propagated or logged

### Code quality
- [ ] Compiles/parses clean with the project's strict flags
- [ ] No new lint errors
- [ ] Linter/formatter applied
- [ ] Names follow project conventions (see project CLAUDE.md)

### Hygiene
- [ ] No commented-out dead code
- [ ] No TODO/FIXME without an owner and tracking
- [ ] Comments explain WHY (when non-obvious), not WHAT
- [ ] Public API changes documented at the call site

## Per-Fleet Gate (before Stop hook allows session close)

- [ ] All tasks have `RESULT_verifier=PASS` evidence in their close
- [ ] Critic reviewed every closure at least once
- [ ] No outstanding CRITICAL critic findings
- [ ] No `REGRESSION-` tasks open
- [ ] Closing report exists (`docs/research/<fleet>/`, `.claude/`, or wherever the project keeps them)
- [ ] Memory updated with any non-obvious lessons learned

## Per-Commit Gate

- [ ] Project tests pass (full suite, not just changed-files)
- [ ] No secrets in diff (.env, credentials, keys, tokens)
- [ ] Commit message states the WHY, not just the WHAT
- [ ] Linked to issue/spec if applicable

## Per-PR Gate

- [ ] CI green
- [ ] Reviewed by critic agent OR human
- [ ] Spec satisfied (if `/spec` was used)
- [ ] No drift between spec and implementation
- [ ] Test plan in PR description is checkable

## How These Are Enforced

| Layer | Where |
|---|---|
| Per-task | TaskCompleted hook calls `verifier` + checks output |
| Per-fleet | Stop hook checks task list + critic log |
| Per-commit | Pre-commit hook (project) — runs tests + secret scan |
| Per-PR | GitHub Actions / CI |

A failing gate at any level **blocks the next layer**. Don't bypass with `--no-verify`.

## Anti-Patterns to Watch For (universal)

- "Looks correct" without running it
- "Tests pass" without showing the output
- "Should work" instead of "I ran it and observed X"
- Mocking the thing under test
- Catching exceptions silently
- Hardcoded paths/IDs that won't survive deploy
- Unbounded loops, queries, retries

Project-specific anti-patterns (e.g., `fprintf(stderr)` in C projects, `SQLITE_TRANSIENT` in SQLite-using projects, `HU_IS_TEST` guards in h-uman) belong in **that project's CLAUDE.md**, not in global rules.

See `~/.claude/extracted-project-rules.md` for rules that were moved out of global on the prune date — apply them to the appropriate project CLAUDE.md.
