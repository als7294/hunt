#!/usr/bin/env bash
# The offline self-checks, exactly as CI runs them (.github/workflows/checks.yml). Usage: scripts/check.sh [test_x.py ...]  (no args = all offline checks)
# Each test_*.py is a plain-assert script that prints "ok". Model-backed checks (CLIP/GeoCLIP weights) are excluded: run them by name.
set -u; cd "$(dirname "$0")/.."
SKIP="test_scan.py test_photo.py test_geo.py test_vlm.py test_clues.py"
tests=("$@"); [ ${#tests[@]} -gt 0 ] || tests=(test_*.py); fail=0
for t in "${tests[@]}"; do case " $SKIP " in *" $t "*) [ $# -eq 0 ] && continue;; esac
  out=$(uv run python "$t" 2>&1) || { echo "FAIL $t"; echo "$out" | tail -5; fail=1; continue; }; echo "ok   $t"; done
[ $fail -eq 0 ] && echo "all checks passed" || { echo "some checks FAILED"; exit 1; }
