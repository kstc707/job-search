#!/usr/bin/env bash
# Every test for the Apply Autofill extension:
#   1. answer-engine unit tests (node --test tests/*.test.js)
#   2. parity: the same questions through answers.py and answers.js must resolve identically
#   3. end-to-end: Chromium loads the unpacked extension and fills the fixture pages
#      (plus the same pages with the content scripts injected directly)
# Usage: tests/run_tests.sh [--all]   (--all also runs the whole auto-apply pytest suite)
# Needs node, and the auto-apply venv (pytest + playwright); Chromium at $REA_CHROMIUM or
# /opt/pw-browsers/chromium-1194/chrome-linux/chrome. AUTOFILL_E2E_MODES=inject skips the
# real-extension run (for browsers that cannot load extensions headless).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
EXT="$(dirname "$HERE")"
AUTO="$(dirname "$EXT")/auto-apply"
PY="${PYTHON:-$AUTO/.venv/bin/python}"

echo "== 1. answer engine unit tests (node)"
node --test --test-reporter=spec "$HERE"/*.test.js

echo "== 2+3. parity with answers.py, end-to-end in Chromium (pytest)"
cd "$EXT"
"$PY" -m pytest -q -p no:cacheprovider tests

if [[ "${1:-}" == "--all" ]]; then
  echo "== auto-apply suite"
  cd "$AUTO"
  "$PY" -m pytest -q -p no:cacheprovider
fi
