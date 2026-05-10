#!/usr/bin/env bash
# SessionEnd hook — append session-final cache stats to telemetry log.
# Delegates to a real Python script so stdin reaches it (heredoc steals stdin).
set -euo pipefail
exec python3 "$HOME/.claude/hooks/_log_cache_stats.py"
