#!/usr/bin/env bash
# SessionStart hook — inject relevant knowledge entries into context.
#
# Reads INDEX.md, picks entries whose tags match the cwd / project, prints them
# to stdout. The harness concatenates this into additionalContext.
#
# Cheap: no LLM, no network. Just grep + head.

set -euo pipefail

INDEX="$HOME/.claude/knowledge/INDEX.md"
[[ -f "$INDEX" ]] || exit 0

# Extract project name from cwd
cwd="$(pwd)"
project="$(basename "$cwd")"

# Pick up to 5 entries from INDEX whose line mentions the project name
# (case-insensitive). If none match, take the 5 most-recent entries.
matches="$(grep -i "$project" "$INDEX" 2>/dev/null | head -5 || true)"
if [[ -z "$matches" ]]; then
  matches="$(grep -E '^- \[' "$INDEX" 2>/dev/null | head -5 || true)"
fi

if [[ -n "$matches" ]]; then
  echo "## Relevant knowledge for this session"
  echo ""
  echo "$matches"
  echo ""
  echo "_(full entries: \`~/.claude/knowledge/\`. Mined via \`/mine-transcripts\`.)_"
fi

exit 0
