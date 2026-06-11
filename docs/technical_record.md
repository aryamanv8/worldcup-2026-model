# WC 2026 Probabilistic Forecasting — Technical Record

> **Purpose of this file.** A condensed, information-dense record of the project's
> methods, decisions, and results — *not* the full paper. Designed to later seed a
> paper-writing prompt: hand this document plus a "write the paper from this"
> instruction to a model and the skeleton and all load-bearing facts are present.
>
> **Author:** Aryaman Verma (CMU; applied math + computational finance).
> **Last updated:** 2026-06-11.
> **Status:** **Stage 1 COMPLETE and validated at tournament level.** Stage 2
> (market-side) in progress: Kalshi data feed, model-vs-market mapping, and
> model-free arbitrage scanners built; no tradeable edge found within Kalshi so far.

---

## 1. One-paragraph summary

A public-data probabilistic forecasting system for the 2026 FIFA Men's World Cup.
Stage 1 produces calibrated match-outcome and tournament forecasts; Stage 2 uses
them as a fair-value reference for detecting prediction-market (Kalshi)
inefficiencies. The match model is a Poisson GLM with a Dixon–Coles correction,
trained on 2000–2026 international results with Elo, squad-value, and form
features. The central Stage-1 methodological result is a diagnostic correction: an
apparent "shrinkage" failure (the model seeming to under-rate top teams vs Elo)
was an artifact of using Elo — itself overconfident at large rating gaps — as
ground truth. A mild residual underconfidence was then removed with a
single-parameter temperature recalibration (T = 0.77), giving pooled OOS match log
loss 0.967. A tournament-level backtest on 2010–2022 subsequently confirmed the
recalibrated model is well-calibrated at the *tournament* level too (it rated every
actual champion a top-3 favorite, ~10.8% mean), establishing that the model needs
no structural change and that the 2026 market's concentration on favorites
(Spain ~16%) is the aggressive side, not the model.

---

## 2. Problem & motivation

- National-team forecasting: sparse fixtures, small per-team samples, high draw
  rates, blowout qualifiers.
- Stage-1 goal: best-*calibrated* public-data model — calibration prioritized over
  raw log loss because Stage 2 needs a trustworthy fair-value reference, not market
  outperformance.
- **Path A** (clean public-data baseline → inefficiency detection) chosen over
  **Path B** (player features + injury data + human overlay).

---

## 3. Data & feature engineering

| Source | Detail |
|---|---|
| International results 2000–2026 | `results.parquet`, 49,378 matches |
| Elo ratings | World Football Elo formulation; `elo_history.parquet` |
| Training matrix | `training_matrix.parquet`, 25,244 matches |
| Transfermarkt squad values | `country_value_history.parquet`, 184 countries × 228 monthly snapshots, via Cloudflare R2 |
| Team features | `team_features.parquet` |

**Squad-value design (load-bearing):** top-23 *mean* value (not sum) to control
TM European coverage bias; monthly snapshots suffice (TM revalues ~twice/yr);
three-way fallback (exact (country, year_month) → earliest prior → population mean
`VALUE_LOG_MEAN`). TM name normalizations: South Korea→"Korea, South"; Bosnia→
"Bosnia-Herzegovina"; Curaçao→"Curacao"; Ivory Coast→"Cote d'Ivoire".

**Team feature columns:** `elo_current`, `elo_12mo_ago`, `elo_trend_12mo`,
`n_matches_12mo`, `gf/ga_per_match_12mo`, `win_rate_12mo`, competitive variants,
`days_since_last_match(_competitive)`, `value_log_eur`, `has_actual_value`,
`confederation`.

---

## 4. Match model architecture

- Independent Poisson goal counts per side, GLM in attacker/defender long format
  (21 parameters); predictors: Elo, log squad value, form, confederation dummies,
  home/neutral, competitive/friendly.
- Dixon–Coles low-score correction; ρ ≈ −0.023 to −0.029 across folds.
- Output: full scoreline probability matrix per match → W/D/L + goal rates.

**Architectural-ceiling negative result:** an `elo_implied_score` feature (sigmoid
of Elo gap/400) got β = 0.186 — significant but ~2 orders of magnitude too small to
reproduce Elo's saturation. A linear-in-features Poisson GLM splits credit across
correlated strength features, so no single feature saturates at extreme gaps. This
motivated (then cancelled, see §5.1) a hierarchical Bayesian rebuild.

---

## 5. Key findings (the spine of the paper)

### 5.1 The Elo-yardstick misdiagnosis

The model appeared to under-price favorites (Spain vs Austria: model 0.58 vs
Elo-implied 0.87, Δ = −0.29; similar for Argentina/Mexico/Spain-vs-SAU). This drove
a planned hierarchical rebuild. **The diagnosis was wrong** — it measured the model
against Elo as if Elo were truth.

### 5.2 Empirical calibration target (script 18)

Binned 25,244 matches by Elo gap; computed empirical expected score per bucket with
bootstrap CIs. The empirical curve **saturates ~0.64** for big favorites (floors
~0.37), while Elo's logistic climbs to ~0.98. At a +330 Elo gap, empirical = 0.641
[0.586, 0.694], n = 237 — the model's 0.58 was nearly right; Elo's 0.87 was the
fantasy. Independent corroboration: the model already beat Elo on log loss (0.973
vs ~1.02). Caveat: Elo noise attenuates the empirical curve (regression dilution),
so true saturation is high-0.60s/low-0.70s — still far from Elo. **Decision:**
hierarchical rebuild cancelled as a shrinkage fix and parked.

### 5.3 Stratified reliability / model card (script 19)

256 held-out matches; overall log loss 0.973, per-class ECE home 0.078 / draw 0.035
/ away 0.035 (well-calibrated aggregate). Binned ECE is upward-biased at small n, so
the robust signal is pooled E_model vs E_real per stratum, which showed mild
*under*confidence (~0.07–0.14 in expected-score terms; top-mid model 0.559 vs real
0.629). Matters for Stage 2: uncorrected underconfidence would manufacture phantom
favorite signals.

### 5.4 Temperature recalibration (script 20)

Power scaling `p' = p^(1/T)/Σ`. Leave-one-WC-out folds: 0.81/0.72/0.81/0.75 (spread
0.09, stable, all < 1). **Production T = 0.77.** OOS pooled log loss 0.9733 →
0.9693; all-data 0.9671; favorite-bias roughly halved at extremes (150..300 |err|
0.099→0.059). Adopted; applied to W/D/L probabilities and propagated into the
simulator (§8).

### 5.5 Tournament-level backtest — the model is NOT too flat (script 25)

After Stage 2 mapping showed the model's 2026 champion numbers (Spain ~8%) running
about half the market's (~16%), a natural hypothesis was tournament-level
compression (small per-match underconfidence compounding over 7 knockout games).
**The backtest refuted this.** Running the full recalibrated simulator on the
2010/14/18/22 World Cups (32-team format, groups reconstructed from match data):

| WC | Actual champion | Model champ prob | Rank (of 32) |
|---|---|---|---|
| 2010 | Spain | 13.6% | 1 |
| 2014 | Germany | 9.6% | 2 |
| 2018 | France | 9.6% | 2 |
| 2022 | Argentina | 10.4% | 2 |

Mean champion probability assigned to the four actual winners: **10.8%**; the actual
champion was a **top-3 favorite in all 4** tournaments (#1 in 2010). A pooled
reliability table across all rounds showed gaps (actual − predicted) of
−0.002 / −0.027 / −0.004 / +0.091 / −0.054 / +0.016 across probability bins — small,
no systematic sign, and the top bin (pred 0.75–1.0) at actual 84.2% vs predicted
82.6% (≈ perfect). **No tournament-level compression.**

**Conclusions:** (i) the model is well-calibrated at the tournament level, not just
match level; (ii) ~10.8% for champions is the correct base rate — champions do not
win at 16% pre-tournament rates; (iii) the 2026 market's concentration on favorites
is the aggressive side (favorite-longshot / narrative bias), and the model's Spain
~8% is sound (slightly below the historical 10–14% mainly because the 48-team format
spreads probability across more teams/games, not new compression); (iv) the planned
strength-recalibration ("option b") is **cancelled** — sharpening to match the
market would degrade a validated model to chase a market bias. This is the quant
loop working: measure on resolved data, let it veto a tempting-but-wrong edit.

---

## 6. Headline results

**Match model (walk-forward 2010/14/18/22, 256 held-out matches):**

| Stage | Pooled WC log loss | Brier |
|---|---|---|
| MVP Poisson + DC | 0.978 | — |
| + squad value, Elo-anchored | 0.9733 ± 0.0247 | 0.5778 |
| + temperature (T=0.77) | 0.9671 | 0.5730 |
| Naive Elo (ref) | ~1.02 | — |
| Sharp bookmaker (ref) | ~0.94–0.96 | — |

**2026 tournament fair values (50k sims, T=0.77):** Spain 7.9%, France 7.2%,
Argentina 6.7%, Brazil 6.7%, England 6.3%. All structural slot-sum/monotonicity
checks exact. **Tournament backtest:** champions averaged 10.8% model prob, top-3
in 4/4 WCs — model validated at tournament level.

---

## 7. Stage 2 — market-side (in progress)

**Strategic frame.** Edge does not come from out-forecasting sharp markets. The
model is a calibrated fair-value reference; edge (if any) comes from (1) monotonicity
arbitrage, (2) cross-platform arbitrage, (3) calibration-aware deviation in the
model's reliable zone. Scope: ~$500, learning-oriented; "learned a lot, ~broke even"
is success.

**Kalshi data feed (script 22).** Public market-data API at
`external-api.kalshi.com/trade-api/v2`, no auth required for reads. Live WC series:
`KXMENWORLDCUP` (winner, 48 markets), `KXWCROUND-26{RO16,QUAR,SEMI,FINAL}` (reach-
round qualifiers, 48 each). ~617 WC contracts total incl. gimmick markets. Trading
(later) requires RSA-PSS auth + US/KYC.

**Model-vs-market mapping (script 23).** Crosswalk Kalshi→model team names by title
parse + small alias map (Congo DR→DR Congo, Czechia→Czech Republic, USA→United
States, Curaçao, IR Iran→Iran, etc.). De-vig per round to its slot count (reach-round
is multi-winner: sum of fair probs = slots). Overround: champion +7.9%, R16 +0.2%,
QF +6.6%, SF +8.5%, final +13.8% — confirming the "Round of 16 Qualifiers" markets
are the 16-team round (de-vig sums match slot counts).

**Model-vs-market read.** Across all rounds the model is systematically LOW on elite
teams (Spain, France, England, Portugal) and HIGH on the mid-tier (Uruguay, Ecuador,
Sweden, Scotland), with mean |edge| growing with depth (0.013 champion → 0.102 R16).
Per §5.5 this is **not** model error — it is the market being aggressive on
favorites. Therefore the outright/round markets are NOT a tradeable model edge: the
model is well-calibrated but the divergence reflects market favorite-longshot bias,
which we will not bet against on liquid contracts.

**Arbitrage scanners (script 24).** Intra-Kalshi monotonicity: **no executable
locks** (nested-round books are internally consistent after spread; only trivial
1-tick soft violations on near-zero contracts). Within-round dutch-book flags
(buy-all-NO) are artifacts of a bid/ask approximation and are pre-fee; expected
negative once real NO-asks and 48-leg fees are applied. **Conclusion: no model-free
edge within Kalshi.** Cross-platform (Kalshi vs Polymarket) is the only remaining
model-free avenue and is currently deferred/unlikely to be pursued.

**Stage-2 status & remaining:** data feed + mapping + scanners done. No tradeable
edge found within Kalshi. Remaining build: (a) fee model — scoped to close the
dutch-book flags rigorously and to produce per-contract net-EV for display, not as a
strategy filter; (b) dashboard — model and market shown as two distinct, legitimate
series (the model's calibration is a feature); (c) commit + record update; then
strategy study (niche markets, alt data) parked for later.

---

## 8. Stage 1 simulator & contract pricing

Simulator (`src/wc2026/simulation/engine.py`, 50k sims): 12 groups → 32-team
knockout → champion; group matches sample full scorelines (tiebreakers), knockout
draws resolve 50/50; hosts get home advantage. **T propagation:** each precomputed
score matrix is reweighted so its W/D/L marginals exactly match the T=0.77 outcome
calibration while preserving conditional scoreline shape — applied once at
precompute, zero changes to bracket logic. Pricing (`scripts/21_contract_pricing.py`):
sim paths → `fair_values_2026.parquet` (fair value + Monte Carlo Wilson CI per
contract); slot-sum and monotonicity checks pass exactly, doubling as the
simulator's structural validation. Tournament-level *statistical* validation comes
from §5.5.

---

## 9. Open questions / threads for the paper

- Regression-dilution correction to pin the true saturation ceiling (§5.2).
- Knockout-vs-group calibration (WC rows lack round labels — minor).
- Un-propagated per-team strength uncertainty (the parked hierarchical model would
  address it). **Note:** §5.5 shows this does not materially hurt tournament
  calibration, so it is a refinement, not a defect.
- **RESOLVED:** "is the model too flat at the tournament level?" — No (§5.5). The
  strength-recalibration idea and the dark-horse-pattern idea are both retired
  (the model already rates eventual deep-runners well; dark-horse pattern-fitting
  would be survivorship-biased overfitting on n=3).
- Cross-platform (Polymarket) arbitrage: untested. Niche markets (halftime
  performer, etc.) and alternative data: parked for a later strategy phase.
- Only genuinely additive model idea remaining: a cheap *manual* injury/availability
  overlay for obvious 2026 absences (the one thing the model structurally can't see).

---

## 10. Reproducibility & engineering notes

- Python + `uv`; pandas, statsmodels, numpy, requests.
- `src/wc2026/`: features (elo, squad_values, team_features, training_matrix),
  models/poisson.py, data (confederations, structure), simulation/engine.py.
- Scripts `01`–`25`. This phase: `09` (match backtest + prediction export),
  `10` (run 2026 sim, applies T, exports per-sim results), `18` (Elo-gap empirical
  calibration), `19` (model card), `20` (temperature recalibration), `21` (contract
  pricing + structural checks), `22` (Kalshi public discovery feed), `23`
  (model-vs-market mapping + de-vig), `24` (model-free arbitrage scanners), `25`
  (tournament-level backtest).
- Key artifacts: `calibration.json` (T=0.77), `fair_values_2026.parquet`,
  `kalshi_wc_contracts.parquet`, `model_vs_market.parquet`, `tournament_backtest.parquet`.
- Bug footnotes: pandas-3.0 StringDtype `merge_asof` mis-join → exact integer join;
  `prepare_design_matrix(return_long=True)`; save-before-OOS-eval; categorical
  columns must be cast to str before ordinal `>=` (pricing) and dropped before
  parquet write (interval `bin` column, script 25); Kalshi `volume_fp` is a decimal
  string (coerce to numeric); Kalshi API host is `external-api.kalshi.com` (older
  `api.kalshi.com` is dead).

---

## 11. Suggested paper structure

1. Intro & motivation (calibration over accuracy for a market-reference model).
2. Data & features (§3).
3. Model (§4) — Poisson + DC; GLM ceiling negative result.
4. Backtest methodology & match results (§6).
5. **Calibration as the core contribution** (§5): Elo-yardstick misdiagnosis →
   empirical curve → stratified reliability → temperature recalibration →
   tournament-level validation. Frame as "validating against a model vs against
   ground truth," with the tournament backtest as the capstone that *also* vetoed an
   intuitive-but-wrong market-matching edit.
6. Simulation & contract fair values (§8).
7. Application: prediction-market analysis — and the honest negative result that no
   tradeable edge exists on liquid Kalshi outrights (market favorite-longshot bias
   vs a calibrated model; no intra-exchange arbitrage) (§7).
8. Limitations & future work (§9).

### Draft seed prompt (expand later)

> "Using the attached technical record, write a rigorous, academic-style research
> paper on a public-data probabilistic forecasting system for the 2026 FIFA World
> Cup. Center the contribution on the calibration methodology — the Elo-yardstick
> misdiagnosis, stratified reliability, temperature recalibration, and the
> tournament-level backtest that validated the model and vetoed a market-matching
> edit. Cover the prediction-market application and the honest finding that no
> tradeable edge exists on liquid markets. Use the results tables verbatim. Keep the
> honest caveats (regression dilution, un-propagated strength uncertainty,
> favorite-longshot interpretation, retail-trading viability). Target
> [venue/length]. Include [methods detail level]."