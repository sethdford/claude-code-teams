# Installation

## Prerequisites

- **Claude Code 2.1.32+** (we use Agent Teams, modify-tool-input hooks, `--bare`, `--include-hook-events`)
  - Check: `claude --version`
- **Python 3.9+** (used by hooks, RL scripts, eval runner)
  - Check: `python3 --version`
- **Bash 3.2+** (macOS default works)
- Optional: `ANTHROPIC_API_KEY` env var (only needed if you want `--bare` mode for headless eval runs; subscription auth works for everything else)

## Install

```bash
git clone https://github.com/USER/claude-code-teams.git
cd claude-code-teams

# Inspect first
ls claude/
cat claude/CLAUDE.md

# Install — symlinks into ~/.claude/, backs up any existing files
./install.sh

# OR non-interactive
./install.sh --yes
```

## Manual settings.json merge (required)

`install.sh` does **not** auto-merge `settings.json` because it would risk clobbering your existing permissions/plugins/env. Open both:

```bash
cat ~/.claude/settings.json.template     # what we provide
cat ~/.claude/settings.json              # your existing
```

Merge by hand, preserving your `permissions`, `enabledPlugins`, and any custom env. The keys you want from our template:

- `statusLine` — custom statusline showing cache hit rate
- `hooks.SessionStart` — knowledge injection + post-compact reminder
- `hooks.SessionEnd` — cache stats + RL session rewards
- `hooks.TaskCompleted` — auto-verify + RL task reward
- `hooks.UserPromptSubmit` — correction signal + completion-claim detector
- `hooks.PreToolUse` (matcher: Bash) — auto-critic on commit
- `hooks.PostToolUse` (matcher: Edit|Write) — auto-eval on agent edit
- `hooks.PreCompact` — compaction logging
- `env.CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE: "70"` — safer compaction headroom

## Restart Claude Code

The statusline and new hooks load on session start. Quit and reopen Claude Code.

## Verify

```bash
./tests/smoke.sh                  # 77+ assertions, no API calls
./tests/e2e/test-verifier.sh      # real claude -p invocation (~$0.05-0.20)
```

A successful smoke gives you `77 passed, 0 failed`.

A successful E2E gives you `RESULT_verifier=PASS` and a transcript at `tests/e2e/runs/<ts>/output.jsonl`.

## Set up scheduled tasks

After restart, install the weekly cadence:

```bash
~/.claude/scripts/setup-scheduled-tasks.sh
```

Creates persistent scheduled tasks via the `schedule` skill:
- Daily 9:13am: `/cache-report` (silent unless anomaly)
- Weekly Mon 9:17am: `/mine-transcripts 7d` (proposes lessons)
- Weekly Mon 9:23am: `/rl-status` (flags tuning candidates)

## Uninstall

```bash
./install.sh --uninstall
```

Removes the symlinks. Your backed-up originals at `*.bak.*` are untouched.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Statusline doesn't appear | Claude Code not restarted | Restart Claude Code |
| `/verify` command not found | Skill discovery cached | Quit and reopen |
| Eval runner returns 401 | `--bare` mode without API key | Use subscription auth (default) or set `ANTHROPIC_API_KEY` |
| Eval runner returns 429 | Subscription rate limit | Wait for reset or use API key |
| Hook claims auto-verifier failed | Auth or budget limit hit | Check `~/.claude/telemetry/auto-verify/*.stderr` |
| Verify-gate blocks task closure | No `RESULT_verifier=` in session | Run `/verify` manually, or add `trivial:` prefix to bypass |
| `_log_cache_stats.py` produces empty file | Stale or unrelated event shape | Check `~/.claude/telemetry/cache-stats.jsonl` for prior records |

## Next

Read [docs/architecture.md](docs/architecture.md) for the full design, or jump to [docs/runbook.md](docs/runbook.md) for daily/weekly cadence.
