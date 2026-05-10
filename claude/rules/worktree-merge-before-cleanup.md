# Worktree Merge-Before-Cleanup Rule

## NEVER call TeamDelete or clean up worktrees before merging agent branches

When agents work in isolated worktrees (`isolation: "worktree"`), their changes exist ONLY in those worktrees. Deleting the worktree deletes the code.

### Required sequence after all agents complete:

1. **List worktree branches**: `git worktree list` and `git branch --list` to find agent branches
2. **Review each branch**: `git log <branch> --oneline` and `git diff main..<branch>` for each
3. **Merge each branch**: `git merge <branch>` or `git cherry-pick` into the target branch
4. **Verify the merge**: `git log --oneline -5` to confirm commits landed
5. **THEN and ONLY THEN**: call TeamDelete or remove worktrees

### Why this rule exists

On 2026-04-04, a 3-agent UX redesign team completed all 6 tasks successfully in isolated worktrees. TeamDelete was called before merging the worktree branches, destroying all agent work. Every change had to be re-implemented from scratch.

### How to apply

Before ANY of these actions, verify all agent branches are merged:
- `TeamDelete`
- `ExitWorktree` with `action: "remove"`
- `git worktree remove`
- Manual deletion of worktree directories
