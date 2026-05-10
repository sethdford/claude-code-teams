#!/usr/bin/env bash
# One-shot setup script — creates the persistent scheduled tasks for the
# weekly cadence: cache-report, mine-transcripts, rl-status.
#
# Run once after restarting Claude Code. Uses claude itself to invoke the
# `schedule` skill with the right cron expressions.
#
# Times chosen to avoid the :00/:30 on-the-hour API rush per Claude's
# scheduling guidance — odd minutes spread load.

set -euo pipefail

echo "=== Setting up scheduled tasks ==="
echo ""
echo "These will be created via the schedule skill:"
echo ""
echo "  Daily 9:13am  → /cache-report   (reports anomalies; silent if healthy)"
echo "  Weekly Mon 9:17am → /mine-transcripts 7d   (proposes lesson diffs)"
echo "  Weekly Mon 9:23am → /rl-status   (flags tuning candidates)"
echo ""
read -p "Proceed? [y/N]: " ok
[[ "$ok" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# We invoke claude with a one-shot prompt that uses the schedule skill.
# Subscription auth handles itself (--bare would require API key).

echo ""
echo "Creating: daily cache-report..."
claude -p \
  "Use the schedule skill to create a recurring task with:
- taskId: daily-cache-report
- cron: '13 9 * * *' (daily at 9:13am local)
- prompt: Run /cache-report. Output the report to ~/.claude/telemetry/cache-reports/<date>.md. Only notify if any anomalies were detected (cache hit rate <70% on any session in the last 24h).
- description: Daily cache hit rate health check" \
  --max-budget-usd 0.10

echo ""
echo "Creating: weekly mine-transcripts..."
claude -p \
  "Use the schedule skill to create a recurring task with:
- taskId: weekly-mine-transcripts
- cron: '17 9 * * 1' (Mondays at 9:17am)
- prompt: Run /mine-transcripts 7d. Review the proposed diffs at ~/.claude/telemetry/mining-runs/<latest>/. Notify with a brief summary of what was found (correction count, pattern count, agent-tuning candidates). Do NOT auto-apply — just surface for review.
- description: Weekly trajectory mining + proposed lesson diffs" \
  --max-budget-usd 0.10

echo ""
echo "Creating: weekly rl-status..."
claude -p \
  "Use the schedule skill to create a recurring task with:
- taskId: weekly-rl-status
- cron: '23 9 * * 1' (Mondays at 9:23am)
- prompt: Run /rl-status. Flag any agents whose 7d mean reward is below 0 or whose trend dropped >0.3 vs 30d. Recommend /tune-agent for them. Notify with a 1-line summary per flagged agent.
- description: Weekly agent reward health snapshot" \
  --max-budget-usd 0.10

echo ""
echo "=== Done ==="
echo ""
echo "Verify with: claude -p 'List my scheduled tasks via the schedule skill'"
