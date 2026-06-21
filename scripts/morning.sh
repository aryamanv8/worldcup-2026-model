#!/usr/bin/env bash
# morning.sh — daily local pipeline for worldcup-2026-model.
#
# WHY THIS EXISTS: Claude's scheduled tasks run in an isolated sandbox that
# CANNOT run `uv` and CANNOT reach the internet (raw.githubusercontent.com for
# results, api.kalshi.com for markets are both blocked). Only your Mac can fetch
# data and run the model. So the Mac does the heavy lifting here and writes the
# outputs into the repo; the Claude "morning routine" task then READS these files
# and does the reasoning / digest / trade_log sync.
#
# Run it manually each morning:    ./scripts/morning.sh
# (or wire it to launchd for hands-free — see docs/handoff.md §5.)
#
# It never fails hard: each step logs and continues, so one network blip doesn't
# block the rest. Everything lands in reports/daily/<date>/.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
DATE="$(date +%F)"
OUT="reports/daily/${DATE}"
mkdir -p "$OUT"
LOG="${OUT}/run.log"
: > "$LOG"

# sizing notional for the pricer's candidate scan (the live experiment uses $500;
# the digest reasoning layer adjusts for actual cash/positions afterwards).
BANKROLL="${BANKROLL:-500}"

step () {  # step "label" cmd...
  local label="$1"; shift
  echo "=== ${label} ===" | tee -a "$LOG"
  if "$@" >>"$LOG" 2>&1; then
    echo "[ok] ${label}" | tee -a "$LOG"
  else
    echo "[FAIL] ${label} (see $LOG)" | tee -a "$LOG"
  fi
  echo "" >> "$LOG"
}

echo "morning.sh — ${DATE}" | tee -a "$LOG"

# 1) settlement side: refresh results, settle due positions, score the model
step "fetch results"        uv run python scripts/01_fetch_results.py
step "settle positions"     uv run python paper_trading/scripts/03_settle.py --auto
step "score live model"     uv run python scripts/28_score_live_predictions.py

# 2) markets side: discover/refresh Kalshi match markets, price vs model (show ALL
#    candidates incl. capped/deferred/out-of-zone so the digest can surface options)
step "discover markets"     uv run python paper_trading/scripts/01_discover_match_markets.py
step "price markets"        uv run python paper_trading/scripts/02_price_match_markets.py \
                                --bankroll "$BANKROLL" --show-all --max-deploy 0.20

# 3) collect today's artifacts for Claude to read
cp -f paper_trading/portfolio.json "$OUT/portfolio.json" 2>>"$LOG" || true
LATEST_SLATE_MD="$(ls -t paper_trading/data/trade_slate_*.md 2>/dev/null | head -1 || true)"
LATEST_SLATE_JSON="$(ls -t paper_trading/data/trade_slate_*.json 2>/dev/null | head -1 || true)"
[ -n "${LATEST_SLATE_MD:-}" ]   && cp -f "$LATEST_SLATE_MD"   "$OUT/trade_slate.md"   2>>"$LOG" || true
[ -n "${LATEST_SLATE_JSON:-}" ] && cp -f "$LATEST_SLATE_JSON" "$OUT/trade_slate.json" 2>>"$LOG" || true

# marker file the Claude task checks ("did today's pipeline run?")
python3 - "$OUT" "$DATE" <<'PY' 2>>"$LOG" || true
import json, sys, datetime
out, date = sys.argv[1], sys.argv[2]
json.dump({"date": date, "generated": datetime.datetime.now().isoformat(),
           "note": "written by scripts/morning.sh on the Mac; read by the Claude morning routine"},
          open(f"{out}/STATUS.json", "w"), indent=2)
PY

echo "" | tee -a "$LOG"
echo "DONE. Outputs in ${OUT}/ — now open Claude and let the morning routine read them." | tee -a "$LOG"
