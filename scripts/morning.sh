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
                                --bankroll "$BANKROLL" --show-all --max-deploy 0.50

# 2b) Strategy v2 sleeves (see docs/strategy_v2.md)
#   - calibration gate writes data/processed/derived_calibration.json (per-market
#     pass flags). Cheap + deterministic; rerunning keeps rho fresh.
#   - goals sleeve (totals/BTTS) priced with the market-blend correction + guards.
#   - progression sleeve needs a fresh outright snapshot (22 -> 23) before pricing.
step "calibrate derived"    uv run python scripts/30_backtest_derived_calibration.py
# BTTS sleeve = TINY LIVE EXPERIMENT only. Script 31 found no robust edge after vig
# (see docs/strategy_v2.md §9), so this is sized small to gather forward evidence,
# restricted to BTTS (the only line we backtested), capped ~2%/trade, ~6% total.
step "price derived"        uv run python paper_trading/scripts/04_price_derived_markets.py \
                                --bankroll "$BANKROLL" --show-all --markets btts \
                                --max-deploy 0.06 --position-cap 0.02
step "discover outrights"   uv run python scripts/22_kalshi_discover.py
step "map model-vs-market"  uv run python scripts/23_map_model_vs_market.py
# Progression sleeve = TINY LIVE EXPERIMENT, currently GATED OFF for entries: its
# model probs come from the frozen pre-tournament sim, which goes stale as teams are
# eliminated (it once suggested Scotland to reach R16 at 1¢). Script 05's staleness
# gate refuses new entries until the live-advancement recompute refreshes the sim;
# it still runs to monitor take-profit on any held positions. Champion take-profit-only.
step "price advance"        uv run python paper_trading/scripts/05_price_advance_markets.py \
                                --bankroll "$BANKROLL" --max-deploy 0.06 --position-cap 0.02

# 2c) Knockout analysis layer (analysis-only; all skip gracefully until inputs exist)
#   - structural arbitrage scan on the live champion/reach board (no bracket needed)
#   - live knockout sim: exact reach-round/champion + continent probs (needs a complete
#     data/processed/knockout_bracket.json — fill r32_order in bracket order)
#   - cross-market consistency: market-internal nesting + live-model-vs-market gaps
step "scan arbitrage"       uv run python scripts/24_scan_arbitrage.py
step "live knockout sim"    uv run python scripts/32_live_knockout_sim.py
step "cross-market check"   uv run python scripts/33_cross_market_consistency.py
cp -f reports/knockout_live_probs.md "$OUT/knockout_live_probs.md" 2>>"$LOG" || true
cp -f reports/cross_market_check.md  "$OUT/cross_market_check.md"  2>>"$LOG" || true

# 3) collect today's artifacts for Claude to read
cp -f paper_trading/portfolio.json "$OUT/portfolio.json" 2>>"$LOG" || true
LATEST_SLATE_MD="$(ls -t paper_trading/data/trade_slate_*.md 2>/dev/null | head -1 || true)"
LATEST_SLATE_JSON="$(ls -t paper_trading/data/trade_slate_*.json 2>/dev/null | head -1 || true)"
[ -n "${LATEST_SLATE_MD:-}" ]   && cp -f "$LATEST_SLATE_MD"   "$OUT/trade_slate.md"   2>>"$LOG" || true
[ -n "${LATEST_SLATE_JSON:-}" ] && cp -f "$LATEST_SLATE_JSON" "$OUT/trade_slate.json" 2>>"$LOG" || true
# v2 sleeve slates + calibration gate
cp -f paper_trading/data/derived_slate.md   "$OUT/derived_slate.md"   2>>"$LOG" || true
cp -f paper_trading/data/derived_slate.json "$OUT/derived_slate.json" 2>>"$LOG" || true
cp -f paper_trading/data/advance_slate.md   "$OUT/advance_slate.md"   2>>"$LOG" || true
cp -f paper_trading/data/advance_slate.json "$OUT/advance_slate.json" 2>>"$LOG" || true
cp -f data/processed/derived_calibration.json "$OUT/derived_calibration.json" 2>>"$LOG" || true

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
