# Self-Improvement Rules

## After Any Correction

When the user corrects your approach or a mistake is discovered:

1. Fix the immediate issue
2. Append the lesson to `.claude/lessons.md` with category and specific pattern
3. If the mistake is repeatable, suggest creating a hookify rule to prevent it

## At Session Start

Review `.claude/lessons.md` for patterns relevant to the current task.

## Error Recovery Protocol

When a command or test fails:

1. Read the full error output — don't guess
2. Check `.claude/lessons.md` for known patterns matching this error
3. If it's a known pattern, apply the documented fix
4. If it's new, fix it and add to lessons

## Deploy Protocol

Before any deploy:

1. Run tests: `pnpm test` in the relevant package
2. Run typecheck: `npx tsc --noEmit` in the relevant package
3. Check `.claude/lessons.md` deploy section for known gotchas
4. Use the deploy script, never raw firebase commands
