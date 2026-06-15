# WC 2026 Probabilistic Forecasting Model

A public-data probabilistic forecasting system for the 2026 FIFA Men's World Cup, built in three stages: a calibrated match-outcome model, a prediction-market analysis layer, and a live paper-trading experiment running through the tournament.

**Author:** Aryaman Verma — Carnegie Mellon University (Applied Math + Computational Finance)  
**Status:** Stages 1 & 2 complete. Stage 3 (paper trading) live through June 2026.

---

## Overview

The project started as a calibration exercise: build the best-calibrated public-data soccer forecasting model, then use it as a fair-value reference against Kalshi prediction markets to look for structural mispricings. The experiment is deliberately honest about what a public-data model can and cannot do.

**Stage 1 — Match model.** A Poisson GLM with a Dixon–Coles low-score correction, trained on ~25,000 international results (2000–2026) with Elo ratings, Transfermarkt squad values, and recent form features. The central methodological contribution is a calibration story: an apparent failure where the model seemed to under-rate top teams turned out to be an artifact of using Elo — itself overconfident at large rating gaps — as the calibration target. A tournament-level backtest on 2010–2022 World Cups confirmed the model is well-calibrated and needs no structural change.

**Stage 2 — Prediction-market analysis.** The calibrated model serves as a fair-value reference against Kalshi's live WC markets (~600 contracts). The model-vs-market gaps on liquid outrights reflect the market's favorite-longshot bias, not model error. No model-free arbitrage exists within Kalshi after fees. The honest result is that no tradeable edge was found on liquid markets.

**Stage 3 — Live paper trading.** A $500 paper-trading experiment on per-match Kalshi markets, running live through the 2026 group stage. Quarter-Kelly sizing, 10% per-position cap, entry only in the model's reliable zone with ≥3¢ net edge after Kalshi taker fees. The experiment's purpose is to let real outcomes adjudicate whether the model-vs-market divergence is genuine edge or the model's known mid-tier lean.

---

## Key results

| Metric | Value |
|---|---|
| Match model OOS log loss (walk-forward 2010–2022, 256 matches) | **0.967** vs Elo baseline ~1.02 |
| Temperature recalibration (T = 0.77) | log loss 0.9733 → **0.9693** |
| Tournament backtest (2010 / 2014 / 2018 / 2022) | actual champion rated **top-3 in 4/4** WCs, mean probability **10.8%** |
| Kalshi intra-exchange arbitrage scan | **no executable locks** after fees |
| Paper trading (live, in progress) | see `paper_trading/trade_log.md` |

**2026 pre-tournament fair values (50k simulations):** Spain 7.9%, France 7.2%, Argentina 6.7%, Brazil 6.7%, England 6.3%.

---

## Repo structure

```
worldcup-2026-model/
│
├── scripts/                           # numbered pipeline scripts
│   ├── 01_fetch_results.py            # pull latest international results
│   ├── 02–10                          # data, Elo, features, model fit, simulation
│   ├── 18_elo_gap_calibration.py      # empirical calibration target (key diagnostic)
│   ├── 19_model_card.py               # stratified reliability analysis
│   ├── 20_temperature_recalibration.py
│   ├── 21_contract_pricing.py         # fair values + structural validation
│   ├── 22–26                          # Kalshi data feed, market mapping, arb scanners
│   ├── 27_export_live_predictions.py  # freeze model predictions (run once)
│   └── 28_score_live_predictions.py   # score frozen predictions vs live results
│
├── src/wc2026/                        # model library
│   ├── features/                      # Elo, squad values, team features, training matrix
│   ├── models/poisson.py              # Poisson GLM + Dixon-Coles
│   └── simulation/engine.py           # tournament simulator (50k paths)
│
├── data/
│   ├── raw/                           # source CSVs (martj42/international_results)
│   └── processed/                     # parquet artifacts: features, backtest, fair values
│
├── paper_trading/                     # Stage 3 — self-contained, does not touch the model
│   ├── README.md                      # portfolio rules and methodology
│   ├── trade_log.md                   # running ledger (open + settled positions)
│   └── scripts/                       # discover → price → settle loop
│
├── docs/
│   └── technical_record.md            # full methods, decisions, results, paper prompt
│
├── dashboard/dashboard.html           # interactive model-vs-market view
└── reports/figures/                   # calibration and model card charts
```

---

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for Python dependency management.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install dependencies
git clone https://github.com/aryamanv8/worldcup-2026-model.git
cd worldcup-2026-model
uv sync

# Refresh match results and re-score live predictions
uv run python scripts/01_fetch_results.py
uv run python scripts/28_score_live_predictions.py
```

The model is frozen for the 2026 tournament. Training scripts (04–10, 17, 20–21) can reproduce the full pipeline from scratch but do not need to be re-run to evaluate live predictions.

---

## Documentation

Full methodological record — data sources, model decisions, calibration findings, market analysis, and a paper-generation prompt for a future write-up — lives in [`docs/technical_record.md`](docs/technical_record.md).

---

## Data sources

- International match results: [martj42/international_results](https://github.com/martj42/international_results)
- Elo ratings: [World Football Elo](https://www.eloratings.net/)
- Squad values: [Transfermarkt](https://www.transfermarkt.com/) (via Cloudflare R2 cache)
- Prediction market prices: [Kalshi](https://kalshi.com/) public API
