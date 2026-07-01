# scripts/ index — what runs daily vs what's frozen

F6 (docs/architecture_audit.md) called for separating the small daily surface from the
one-time Stage-1 build/debug scripts. Rather than physically relocate the frozen scripts
(they all resolve the repo root via `Path(__file__).resolve().parents[1]`, so moving them
into a subfolder would break that and churn 7 frozen files), this index does the
separation. Numbering has gaps — that's expected.

## DAILY — the live pipeline (run by `scripts/morning.sh`, in order)
These are the only scripts that run every morning. This is the surface to care about.

- `01_fetch_results.py` — refresh match results.
- `28_score_live_predictions.py` — score the frozen model vs actuals.
- `34_market_inventory.py` — **unified Kalshi discovery + market map** (replaces 22).
- `32_live_knockout_sim.py` — exact bracket-DP → live reach/champion probs.
- `23_map_model_vs_market.py` — melt live sim vs market (reads full inventory).
- `24_scan_arbitrage.py` — structural arb scan (net of fees).
- `33_cross_market_consistency.py` — market nesting + live-model-vs-market gaps.
- `30_backtest_derived_calibration.py` — per-line calibration gate (cheap, deterministic).
- (plus `paper_trading/scripts/` 01 discover · 02 price moneyline · 03 settle ·
  04 price derived · 05 price advance — see that folder.)

## STAGE-1 — frozen model build (DO NOT re-run mid-tournament)
Built the frozen model + features; re-running mid-tournament is a no-op at best and a
model change at worst. CLAUDE.md forbids running 04–10, 17, 20–21, 25.

- `02_compute_elo` · `03_load_wc_structure` · `04_build_team_features` ·
  `05_build_training_matrix` · `06_fit_poisson` · `08_fit_dixon_coles` ·
  `10_run_simulation` · `13_build_squad_value_history` · `17_rebuild_team_features_parquet` ·
  `18_elo_gap_calibration` · `19_model_card` · `20_temperature_recalibration`.

## BACKTEST / ANALYSIS — occasional, not daily
- `09_backtest_world_cups` · `25_backtest_tournament` · `26_fee_model` ·
  `27_export_live_predictions` · `29_backtest_trading_strategy` ·
  `31_backtest_derived_strategy`.

## DEBUG / DIAGNOSTIC — one-off, safe to ignore
Verified 2026-07-01 as unreferenced by any pipeline or code.

- `07_sanity_check_predictions` · `11_diagnose_predictions` · `12_explore_transfermarkt` ·
  `14_verify_value_merge` · `15_audit_value_history` · `16_diagnose_merge_dtype` ·
  `fetch_goals_odds.py` (O/U scraper — shelved, see handoff §0).

## DEPRECATED
- `21_contract_pricing` — superseded (fair values now come from the live sim via 05).
- `22_kalshi_discover` — superseded by `34_market_inventory.py`; deletable.
