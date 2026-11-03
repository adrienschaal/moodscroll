#!/bin/bash
# MOODscroll installer for macOS on Apple Silicon. Safe to run again to update.
#
#   curl -fsSL https://raw.githubusercontent.com/adrienschaal/moodscroll/main/install.sh | bash
#   or, from a clone:  ./install.sh
set -euo pipefail

say()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
done_() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
die()  { printf '\n\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

say "MOODscroll installer"

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] \
  || die "MOODscroll needs a Mac with Apple Silicon (M1 or later)."

# Apple's command line tools: git, and the Swift compiler for the OCR helper.
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install >/dev/null 2>&1 || true
  die "Install Apple's Command Line Tools in the window that just opened, then run this again."
fi
done_ "Apple Command Line Tools"

command -v brew >/dev/null 2>&1 || [ -x /opt/homebrew/bin/brew ] \
  || die "Install Homebrew first (one line, from https://brew.sh), then run this again."
eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || brew shellenv)"
for pkg in uv ffmpeg; do
  if ! command -v "$pkg" >/dev/null 2>&1; then
    say "Installing $pkg"
    brew install "$pkg"
  fi
  done_ "$pkg"
done

# Use this folder if we're inside a clone, otherwise download (or update) one.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && grep -q '^name = "moodscroll"' "$HERE/pyproject.toml" 2>/dev/null; then
  REPO="$HERE"
else
  REPO="$HOME/.local/share/moodscroll"
  if [ -d "$REPO/.git" ]; then
    git -C "$REPO" pull --ff-only --quiet
  else
    git clone --quiet https://github.com/adrienschaal/moodscroll "$REPO"
  fi
fi
done_ "code in $REPO"

say "Installing Python and dependencies (first time: a minute or two)"
uv sync --project "$REPO" --frozen --quiet
done_ "ready"

# The rest asks questions, so read answers from the keyboard even when this
# script itself arrived through a pipe (curl … | bash).
uv run --project "$REPO" moodscroll-setup "$@" < /dev/tty
