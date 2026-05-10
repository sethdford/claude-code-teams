# Tool Creation Protocol

## When to Create a New Tool

When you find yourself repeating a multi-step pattern 3+ times, create a tool:

1. **Hook** — if the pattern should run automatically on an event (e.g., PreToolUse, PostToolUse)
2. **Skill** — if the pattern is invoked by the user (e.g., /deploy, /audit)
3. **Script** — if the pattern is a bash workflow (add to `scripts/`)
4. **Rule** — if the pattern is a convention to follow (add to `.claude/rules/`)

## Tool Creation Checklist

- [ ] Does this tool already exist? Check `.claude/rules/`, `.claude/agents/`, `scripts/`
- [ ] Is it genuinely reusable (will happen again)?
- [ ] Is the trigger clear (when should it run)?
- [ ] Does it have a clear input/output contract?
- [ ] Is it tested or at minimum smoke-tested?

## Meta-Programming Patterns

- If a deploy step keeps failing, write a hook that checks preconditions
- If a test pattern is repeated, write a test generator script
- If a review finds the same issue, write a hookify rule
- If context is wasted on the same exploration, write it into a rule file

## File Locations

- Hooks: `.claude/hooks/` (bash scripts, must be executable)
- Rules: `.claude/rules/` (markdown, auto-loaded every session)
- Agents: `.claude/agents/` (markdown with frontmatter)
- Skills: via plugins (Superpowers, etc.)
- Scripts: `scripts/` (project-level automation)
