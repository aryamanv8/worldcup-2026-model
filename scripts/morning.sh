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
# restricted to BTTS (the only line we backtested).
# 2026-06-29: position cap raised 0.02 -> 0.05 so quarter-Kelly governs sizing rather
# than an artificial 2% truncation (qK on a ~3c BTTS edge is itself ~2%, so this
# changes size only marginally). Deploy still capped ~6%. Revert to 0.02 to restore
# the original tiny-experiment truncation.
step "price derived"        uv run python paper_trading/scripts/04_price_derived_markets.py \
                                --bankroll "$BANKROLL" --show-all --markets btts \
                                --max-deploy 0.06 --position-cap 0.05
step "market inventory"     uv run python scripts/34_market_inventory.py
# Live knockout sim MUST run BEFORE script 23 and the advance pricer: it is now the single
# MODEL source for progression markets (F1 in docs/architecture_audit.md). It rolls the
# ACTUAL 32-team bracket forward through the frozen match model (exact DP), writing
# data/processed/tournament_probs_live.parquet — eliminated teams drop out, reach-round
# probs stay current. Script 23 melts this into model_vs_market; 05/24/33 all read that.
step "live knockout sim"    uv run python scripts/32_live_knockout_sim.py
step "map model-vs-market"  uv run python scripts/23_map_model_vs_market.py
# Progression sleeve = TINY LIVE EXPERIMENT. Previously gated off because its probs came
# from the frozen pre-tournament sim; now wired to the live sim, so entries are allowed
# again (still corrected toward market, +3c gate, divergence-guarded, tiny-sized).
# Champion is take-profit-only. Expect a near-empty slate — reach markets are efficient.
step "price advance"        uv run python paper_trading/scripts/05_price_advance_markets.py \
                                --bankroll "$BANKROLL" --max-deploy 0.06 --position-cap 0.02

# 2c) Knockout analysis layer (analysis-only; all skip gracefully until inputs exist)
#   - structural arbitrage scan on the live champion/reach board (no bracket needed)
#   - cross-market consistency: market-internal nesting + live-model-vs-market gaps
step "scan arbitrage"       uv run python scripts/24_scan_arbitrage.py
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

# 4) retention: keep only the last N days of reports/daily/ so it doesn't grow forever.
#    (Regenerated + gitignored; the decision log + docs hold anything durable.)
#    Portable across BSD/macOS head (no `head -n -N`): dirs are date-named, so sort =
#    chronological (oldest first); delete the (total - N) oldest.
RETAIN_DAYS="${RETAIN_DAYS:-30}"
if [ -d reports/daily ]; then
  dirs="$(ls -1d reports/daily/*/ 2>/dev/null | sort)"
  total="$(printf '%s\n' "$dirs" | grep -c . || true)"
  if [ "${total:-0}" -gt "$RETAIN_DAYS" ]; then
    printf '%s\n' "$dirs" | head -n "$((total - RETAIN_DAYS))" | while read -r old; do
      [ -n "$old" ] && rm -rf "$old" && echo "[retention] pruned ${old}" >> "$LOG"
    done
  fi
fi

echo "" | tee -a "$LOG"
echo "DONE. Outputs in ${OUT}/ — now open Claude and let the morning routine read them." | tee -a "$LOG"
