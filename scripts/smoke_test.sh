#!/usr/bin/env bash
# Smoke test: generate demo data, run baseline → run → report. Exits 0 if WaveOS works.
# Requires: pip install -e . (so "waveos" is on PATH)
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
DEMO_DIR="${DEMO_DIR:-out/demo_data}"
OUT_DIR="${OUT_DIR:-out/smoke_run}"

if ! command -v waveos &>/dev/null; then
  echo "waveos not found. Run: pip install -e ."
  exit 1
fi

# Use CI/test license so smoke test runs without a real license (override with WAVEOS_LICENSE_KEY or WAVEOS_LICENSE_SKIP=1)
export WAVEOS_LICENSE_KEY="${WAVEOS_LICENSE_KEY:-WAVEOS-CI-20991231-TEST}"

echo "Smoke test: sim → baseline → run → report"
waveos sim --out "$DEMO_DIR"
waveos baseline --in "$DEMO_DIR/baseline"
waveos run --in "$DEMO_DIR/run" --baseline "$DEMO_DIR/baseline" --out "$OUT_DIR"
waveos report --in "$OUT_DIR"

if [[ -f "$OUT_DIR/health_summary.json" ]] && [[ -f "$OUT_DIR/report.html" ]]; then
  echo "Smoke test OK: $OUT_DIR/health_summary.json and report.html present"
else
  echo "Smoke test FAIL: expected health_summary.json and report.html in $OUT_DIR"
  exit 1
fi

# Optional: verify output content (--verify) so we know WaveOS did what it should, not just that files exist
if [[ "${1:-}" == "--verify" ]]; then
  echo "Verifying output content..."
  fail=0
  if ! [[ -s "$OUT_DIR/events.jsonl" ]]; then
    echo "FAIL: events.jsonl missing or empty"
    fail=1
  else
    echo "  OK: events.jsonl has content"
  fi
  if ! [[ -s "$OUT_DIR/report.html" ]]; then
    echo "FAIL: report.html missing or empty"
    fail=1
  else
    echo "  OK: report.html non-empty"
  fi
  if [[ -f "$OUT_DIR/health_summary.json" ]]; then
    if ! python3 -c "
import json, sys
from pathlib import Path
p = Path(\"$OUT_DIR/health_summary.json\")
d = json.loads(p.read_text())
items = d if isinstance(d, list) else d.get('entities', d) or d.get('summary', [])
if not items and not isinstance(d, dict):
    items = [d]
for e in (items if isinstance(items, list) else [items]):
    if isinstance(e, dict) and ('entity_id' in e or 'status' in e or 'score' in e):
        print('OK: health_summary has entity-like entries')
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
      echo "FAIL: health_summary.json has no entity/status/score structure"
      fail=1
    else
      echo "  OK: health_summary has entity/status/score structure"
    fi
  else
    echo "FAIL: health_summary.json missing"
    fail=1
  fi
  if [[ $fail -eq 1 ]]; then
    echo "Verification failed."
    exit 1
  fi
  echo "All verification checks passed."
fi
