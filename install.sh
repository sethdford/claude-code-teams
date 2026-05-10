#!/usr/bin/env bash
# install.sh — Symlink claude-code-teams into ~/.claude/.
#
# Idempotent: safe to re-run. Backs up any existing ~/.claude/CLAUDE.md /
# settings.json with a timestamp. Files in claude/ are symlinked rather than
# copied so updates flow through.
#
# Usage:
#   ./install.sh              # interactive (prompts before each destructive op)
#   ./install.sh --yes        # non-interactive (CI)
#   ./install.sh --uninstall  # remove all symlinks
set -euo pipefail

YES=0
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/claude"
DEST="$HOME/.claude"
TS="$(date +%Y%m%d-%H%M%S)"

confirm() { (( YES )) && return 0; read -rp "$1 [y/N]: " r; [[ "$r" =~ ^[Yy]$ ]]; }
backup_if_real() {
  local f="$1"
  if [[ -e "$f" && ! -L "$f" ]]; then
    cp -a "$f" "${f}.bak.${TS}"
    echo "  backed up → ${f}.bak.${TS}"
  fi
}

if (( UNINSTALL )); then
  echo "Uninstalling claude-code-teams symlinks from $DEST..."
  for sub in skills agents rules hooks evals rl knowledge statusline scripts sandbox; do
    [[ -L "$DEST/$sub" ]] && { rm "$DEST/$sub"; echo "  removed $DEST/$sub"; }
  done
  for f in CLAUDE.md settings.json.template; do
    [[ -L "$DEST/$f" ]] && { rm "$DEST/$f"; echo "  removed $DEST/$f"; }
  done
  echo "Done. (Your backed-up originals at *.bak.* are untouched.)"
  exit 0
fi

mkdir -p "$DEST"
echo "Installing claude-code-teams from $SRC into $DEST..."
echo ""

# Symlink directories that don't exist or already contain our content
for sub in skills agents rules hooks evals rl knowledge statusline scripts sandbox; do
  if [[ -e "$DEST/$sub" && ! -L "$DEST/$sub" ]]; then
    echo "WARN: $DEST/$sub exists and is not a symlink."
    if confirm "  Move existing $DEST/$sub to ${DEST}/${sub}.bak.${TS} and symlink in?"; then
      mv "$DEST/$sub" "${DEST}/${sub}.bak.${TS}"
      ln -s "$SRC/$sub" "$DEST/$sub"
      echo "  symlinked $DEST/$sub → $SRC/$sub (original at ${DEST}/${sub}.bak.${TS})"
    else
      echo "  skipped $DEST/$sub"
    fi
  elif [[ -L "$DEST/$sub" ]]; then
    ln -sfn "$SRC/$sub" "$DEST/$sub"
    echo "  symlink $DEST/$sub (refreshed)"
  else
    ln -s "$SRC/$sub" "$DEST/$sub"
    echo "  symlinked $DEST/$sub → $SRC/$sub"
  fi
done

# CLAUDE.md — only install if user has none
if [[ ! -e "$DEST/CLAUDE.md" ]]; then
  ln -s "$SRC/CLAUDE.md" "$DEST/CLAUDE.md"
  echo "  installed CLAUDE.md (symlink)"
elif [[ -L "$DEST/CLAUDE.md" ]]; then
  ln -sfn "$SRC/CLAUDE.md" "$DEST/CLAUDE.md"
  echo "  refreshed CLAUDE.md symlink"
else
  echo "  $DEST/CLAUDE.md exists and is not a symlink — leaving as-is."
  echo "    To use ours: mv $DEST/CLAUDE.md $DEST/CLAUDE.md.bak.${TS}; ln -s $SRC/CLAUDE.md $DEST/CLAUDE.md"
fi

# settings.json — never auto-merge. Provide template, user merges manually.
if [[ ! -e "$DEST/settings.json.template" ]]; then
  ln -s "$SRC/settings.json.template" "$DEST/settings.json.template"
  echo "  installed settings.json.template (symlink)"
fi

echo ""
echo "=== Installed ==="
echo ""
echo "Next steps:"
echo "  1. Merge $DEST/settings.json.template into your $DEST/settings.json"
echo "     (preserves your existing permissions/plugins; adds our hooks + statusline)"
echo "  2. Restart Claude Code to activate hooks + statusline + new skills"
echo "  3. Run ./tests/smoke.sh to verify the install"
echo "  4. Run $DEST/scripts/setup-scheduled-tasks.sh to install weekly tasks"
echo ""
echo "Uninstall: ./install.sh --uninstall"
