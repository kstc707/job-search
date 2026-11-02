#!/usr/bin/env bash
# Build a resume PDF from a .tex file that does \input{preamble}, then run layout checks.
# Usage: bash build.sh path/to/resume.tex
set -u
TEX="$1"
DIR="$(cd "$(dirname "$TEX")" && pwd)"
BASE="$(basename "$TEX" .tex)"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cp -n "$SKILL_DIR/templates/preamble.tex" "$DIR/preamble.tex" 2>/dev/null || true

if ! command -v pdflatex >/dev/null; then
  echo "pdflatex missing: install with apt-get install -y texlive-latex-base texlive-latex-extra texlive-fonts-recommended"
  exit 1
fi

cd "$DIR"
pdflatex -interaction=nonstopmode "$BASE.tex" >/dev/null 2>&1
grep -E "^!" "$BASE.log" && { echo "LaTeX error, see $BASE.log"; exit 1; }
grep -E "Overfull" "$BASE.log" && echo "WARNING: overfull line (text sticks out), reword it"

PAGES=$(pdfinfo "$BASE.pdf" | awk '/^Pages/{print $2}')
echo "Pages: $PAGES"

echo "--- Lines that end a bullet with only a word or two (reword so the line is full or ends cleanly):"
pdftotext -layout "$BASE.pdf" - | awk 'length($0)>0 && length($0)<40 && $0 ~ /^  [a-z0-9$(]/'

if [ "$PAGES" -gt 1 ]; then
  echo "--- Bottom of page 1 (must be filled to the bottom margin, no forced break):"
  pdftotext -layout -f 1 -l 1 "$BASE.pdf" - | tail -3
  echo "--- Top of page 2 (should start at a project or role heading, not mid-bullet):"
  pdftotext -layout -f 2 -l 2 "$BASE.pdf" - | head -2
fi
echo "PDF: $DIR/$BASE.pdf"
