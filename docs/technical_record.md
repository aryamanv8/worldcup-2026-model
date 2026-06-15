# WC 2026 Probabilistic Forecasting — Technical Record

> **Purpose of this file.** A condensed, information-dense record of the project's
> methods, decisions, and results — *not* the full paper. Designed to later seed a
> paper-writing prompt: hand this document plus a "write the paper from this"
> instruction to a model and the skeleton and all load-bearing facts are present.
>
> **Author:** Aryaman Verma (CMU; applied math + computational finance).
> **Last updated:** 2026-06-15.
> **Status:** **Stage 1 COMPLETE and validated at tournament level. Stage 2
> (market-side) COMPLETE** — Kalshi data feed, model-vs-market mapping, fee model,
> model-free arbitrage scanners, and dashboard built; no tradeable edge found on
> liquid Kalshi outrights/round markets. **Stage 3 (live $500 paper-trading
> experiment on per-match markets) IN PROGRESS**, started 2026-06-12 — see §12.
> **Live model validation (§13) IN PROGRESS** — frozen model predictions scored
> against real 2026 results as the tournament unfolds.

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

## 7. Stage 2 — market-side (COMPLETE)

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

**Stage-2 status & remaining (CLOSED OUT).** Data feed + mapping + scanners + fee
model + dashboard all built and committed:
- **Fee model** — implemented in `paper_trading/scripts/02_price_match_markets.py`
  (`ceil(0.07·C·P·(1−P))`), used both to close out the dutch-book flags (negative
  after real fees) and as the Stage-3 entry gate's net-EV filter.
- **Dashboard** — `dashboard/dashboard.html`, showing model and market as two
  distinct, legitimate series (the model's calibration is a feature, not a flaw).
- No tradeable edge found within Kalshi outrights/round markets.

Remaining: cross-platform arbitrage and niche-market/alt-data strategy study remain
parked for a later phase (not on the critical path; Stage 3 below is now the active
work).

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
8. Live paper-trading experiment — brief overview only (§12.3 summary table); not
   the focus of the paper. State hypothesis, rules, final P&L, and verdict in ~0.5
   pages. Detailed trade log lives in `trade_log.md`.
9. Live model validation: final log loss vs baselines (§13.2).
10. Limitations & future work (§9).

---

## 12. Stage 3 — Live paper-trading experiment (in progress)

A capital-free paper-trading experiment that operationalizes the Stage 1 model and
the Stage 2 findings. **No real money.** With capital removed, the model-vs-market
divergences (§7) stop being a go/no-go question and become a clean experiment: trade
the model's signal on paper across the tournament and let real outcomes adjudicate
whether the divergence is genuine edge or the model's mid-tier lean.

**Self-contained** in `paper_trading/` (`README.md` methodology, `trade_log.md`
running ledger, `scripts/`, `data/`); does not modify the model pipeline.

**Venue priority.** Per-match markets are primary — the model's most-validated
ground (OOS log loss 0.967; calibrated; champions rated top-3 in §5.5) and the
fastest feedback (hours, not weeks). A diversified slice of reach-round value picks
tests the headline divergence directly.

**Portfolio rules.** $500 paper bankroll; quarter-Kelly sizing
`size = 0.25 × ((p − a)/(1 − a)) × bankroll` (full Kelly over-bets because `p` is
estimated); 10% per-position cap; skip stakes < $5; entry only where the model is in
a reliable zone AND net edge ≥ 3¢/contract after Kalshi taker fees
`ceil(0.07·C·P·(1−P))`.

**Loop.** discover → price (model FV + reliability zone) → filter (net edge) →
log → settle at real outcome → review and attribute P&L.

**Expected outcome (hypothesis).** If match markets are as efficient as the
outrights, paper P&L grinds to break-even-after-fees ("a calibrated model still
can't beat an efficient market after costs"). If lower-attention group-stage match
markets carry a soft pocket, the loop should surface it. Either is a documentable
result; this section will be updated with the realized P&L and the verdict as the
tournament progresses.

### 12.1 Execution tooling & Day-1 book (2026-06-13)

**Tooling.** `paper_trading/scripts/`: `01_discover_match_markets.py` (open KXWC*
markets → fixtures, date-windowed), `02_price_match_markets.py` (frozen T=0.77 model
→ per-fixture moneyline fair value via `recalibrate_score_matrix`; reliable-zone gate
+ fee model + quarter-Kelly; one position per match; total-deployment cap), and
`03_settle.py` (books regulation results into `portfolio.json`, rolls bankroll,
appends `calibration_log.csv`). Model frozen for the tournament — all trades
attributable to one model.

**Reliable-zone operationalization (load-bearing).** The committed `model_card.json`
flags *every* stratum `reliable=false`: its rule (max-per-class ECE ≤ 0.05) is
unreachable at n ≤ 70 (binned ECE is upward-biased at small n), and it is the
pre-temperature card. The entry gate was therefore redefined onto the robust signal
of §5.2/§5.3: in-zone iff the Elo-gap bucket has n ≥ 30 and |E_model − E_real| ≤ 0.05.
In-zone buckets: −50..50 (|Δ|=0.041), 50..150 (|Δ|=0.006); wider-gap buckets out.
Pending refinement: regenerate the card on `backtest_predictions_recalibrated.parquet`.

**Entry rule.** Reliable zone AND net edge ≥ 3¢/contract after taker fee
`ceil(0.07·C·P·(1−P))` AND stake ≥ $5; quarter-Kelly; 10% per-position cap; one
position per match (NO-favorite + YES-underdog + YES-draw are the same directional
bet); total-deployment guard. `model_fv` recorded for the side actually bet
(NO = complement) for calibration-log coherence.

**Day-1 observation (sharpens §7).** Within the reliable zone the qualifying trades
are dominated by the same favorite-underconfidence found on the outrights — the model
rates the market favorite lower than the market. Bucket-average calibration cannot
separate genuine edge from this mid-tier lean *within* a calibrated bucket, so the
staked basket is effectively one correlated thesis (favorite-fade), deliberately
sized small and tagged for attribution. The zone still does necessary work: it
excludes extreme-gap games where the model is plainly wrong (e.g. Spain 63% vs
market 91%).

**Opening book (4 positions entered 2026-06-12/13, $110.41 = 22% of $500).**

| # | Match | Bet | Entry ¢ | Qty | Cost $ | Model FV % | Net edge ¢ | Tag | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Brazil vs Morocco | NO Brazil | 42 | 27 | 11.81 | 47.4 | +3.7 | reliable | **WIN** (1-1 draw, 2026-06-13), +$15.19 |
| 2 | Austria vs Jordan | NO Austria | 27 | 101 | 28.67 | 43.0 | +14.6 | favorite-fade | OPEN, settles 2026-06-17 |
| 3 | Turkiye vs Paraguay | YES Paraguay | 24 | 125 | 31.60 | 42.3 | +17.0 | favorite-fade | OPEN, settles 2026-06-19 |
| 4 | Ecuador vs Germany | NO Germany | 45 | 82 | 38.33 | 61.4 | +14.7 | favorite-fade | OPEN, settles 2026-06-25 |

Settlement is regulation time (matches Kalshi KXWCGAME). Full ledger: `paper_trading/trade_log.md`.

### 12.2 Settlement entries (running)

**#1 — Brazil vs Morocco (settled 2026-06-14).** Result: 1-1 draw (Saibari 21',
Vinicius Jr 32'; MetLife Stadium). NO @ Brazil → **WIN**. Payoff $27.00 on $11.81
cost. Realized P&L: **+$15.19**. Bankroll: $500.00 → $515.19.

*Interpretation caveat:* tagged `reliable`, Elo +78 near-even matchup — not part of
the `favorite-fade` basket. A single win on a coin-flip market is uninformative about
the thesis; the three open `favorite-fade` positions are what bear on the experiment.

**#2 — Austria vs Jordan (settles 2026-06-17).** [To be filled.]

**#3 — Turkiye vs Paraguay (settles 2026-06-19).** [To be filled.]

**#4 — Ecuador vs Germany (settles 2026-06-25).** [To be filled.]

### 12.3 Final book summary [fill at tournament end — paper pulls from here]

| Metric | Value |
|---|---|
| Total positions | [TBD] |
| Settled | [TBD] |
| Won / Lost | [TBD] |
| Win rate | [TBD] |
| Total cost (all positions) | [TBD] |
| Total payoff | [TBD] |
| Realized P&L | [TBD] |
| Final equity | [TBD] |
| Favorite-fade win rate | [TBD] / [TBD] |
| Verdict | [TBD: edge confirmed / noise / thesis rejected] |

**Narrative verdict [fill at end]:** [Did the favorite-fade basket outperform,
underperform, or land near zero after fees? One paragraph for the paper.]

## 13. Live 2026 tracking (in progress)

A parallel, capital-free validation track, independent of the paper-trading
experiment: as the actual 2026 tournament unfolds, the frozen model's
pre-match predictions are scored against real results — the first genuinely
live (never-seen) test of this model.

**Methodology.** `scripts/27_export_live_predictions.py` (run once,
write-protected) runs the frozen model (T=0.77, rho=-0.0246) through the same
`predict_match_dc` -> `recalibrate_score_matrix` -> W/D/L path used everywhere
else, for all 72 group-stage fixtures sourced directly from `results.parquet`
(exact dates/matchups). Home advantage replicates the simulator's rule exactly
(only Mexico/Canada/USA, only in their own group matches). Output:
`live_2026_predictions.parquet`, a fixed yardstick frozen alongside the model.

`scripts/28_score_live_predictions.py` (re-run every few days, after
`01_fetch_results.py`) joins these frozen predictions against current results,
scores played matches (top-pick accuracy, log loss, Brier vs flat/base-rate
baselines), and appends a dated snapshot to `live_2026_scorecard_log.csv`.

**Day-1 status (2026-06-15, n=8).** Top-pick accuracy 3/8 (37.5%); mean log
loss 1.104 vs historical OOS 0.967. At n=8 this is noise, not a finding —
flagged explicitly by the script. One structural note: 3 of the 5 misses were
draws, and the model never assigns "draw" the highest W/D/L probability across
these 8 matches — a known property of argmax scoring on W/D/L outputs, not a
defect (e.g. Brazil/Morocco's 25.9% draw probability was real and substantial,
just not the largest of the three).

### 13.1 Scorecard log (running)

Re-run `01_fetch_results.py` then `28_score_live_predictions.py` every few days.
Log appends to `data/processed/live_2026_scorecard_log.csv`.

| Run date | n scored | Top-pick acc | Mean log loss | Binary log loss | Note |
|---|---|---|---|---|---|
| 2026-06-15 | 8 / 72 | 37.5% | 1.104 | 0.642 | Day 1; n too small for inference |
| [next run] | | | | | |

### 13.2 Final validation results [fill at end — paper pulls from here]

| Metric | Value | Baseline |
|---|---|---|
| n matches scored | [TBD] / 72 | — |
| Top-pick accuracy | [TBD]% | 33.3% (uniform) |
| Mean log loss (3-way) | [TBD] | 1.099 (uniform) / 0.974 (base rate) |
| Binary log loss (per-leg) | [TBD] | 0.693 (coin flip) |
| Brier score | [TBD] | — |

**Narrative [fill at end]:** [One paragraph: did the frozen model beat baselines
at n=72? Draw under-rating confirmed or noise? Any systematic failure modes?]

---

## 14. Paper-generation prompt

> **How to use.** Once the tournament is over and §12.3 and §13.2 are filled in,
> paste this entire technical record into a new Claude conversation, followed by
> the prompt below. Also attach `paper_trading/trade_log.md` for the final P&L
> numbers and `data/processed/live_2026_scorecard_log.csv` for the final
> validation row.

---

```
I'm going to give you a technical record documenting a complete data science
project — a probabilistic forecasting system for the 2026 FIFA World Cup and
its application to prediction-market analysis. Please write the paper described
below from that record.

**Output format.** A single LaTeX file, article class, 11pt, a4paper margins,
no journal-submission formatting (no abstract keywords, no author affiliations
beyond "Aryaman Verma, Carnegie Mellon University"). Use the following packages:
amsmath, booktabs, graphicx, hyperref, microtype, geometry (2.5cm margins),
parskip. Tables: booktabs style (\toprule / \midrule / \bottomrule). Internal
cross-references via \label{} and \ref{}. No custom theorem environments or
colored boxes.

**Tone and audience.** Academically honest, first-person, concise. No filler
phrases ("it is worth noting that", "as we can see"). Caveats are not
disclaimers to bury — they are substantive methodological points; present them
in-line. Audience: technically literate reader (ML/stats/quant finance
background). No tutorial-level probability or statistics.

**Length.** 8–12 pages, not counting any appendix.

**Paper structure and section weights:**

1. Abstract (~150 words). Summarize the model, the central calibration
   finding (Elo-yardstick misdiagnosis), the market-analysis result (no
   tradeable edge on liquid outrights), and the live paper-trading verdict.

2. Introduction (~0.5 page). Motivation: why calibration is the right
   objective for a market-reference model, not raw log loss. Briefly frame
   the three stages. Cite Dixon & Coles (1997) and the World Football Elo
   rating system.

3. Data and Features (~0.5 page). Source the details from §3 of the record.
   Present the squad-value design decisions (mean vs sum, fallback logic)
   concisely; these are load-bearing and worth one sentence each. The feature
   table from §3 can be reproduced verbatim.

4. Model (~0.5 page). Source from §4. Cover the Poisson GLM + Dixon-Coles
   architecture, the ρ estimate, and the architectural-ceiling negative result
   (the elo_implied_score feature). Do not over-expand this section — the
   model is standard; the calibration work is the contribution.

5. Calibration methodology (~2 pages). This is the core of the paper.
   Structure it as a single narrative arc with four beats:
   a. The apparent failure: model under-rates favorites vs Elo (§5.1).
   b. The diagnostic correction: Elo is the overconfident party (§5.2) —
      include the empirical saturation numbers and the regression-dilution
      caveat.
   c. Stratified reliability and mild residual underconfidence (§5.3) —
      include the ECE numbers and the important note that binned ECE is
      upward-biased at small n.
   d. Temperature recalibration (§5.4) — T=0.77, the log loss improvement,
      and the fold-stability check. Then the tournament-level backtest (§5.5)
      as the capstone: reproduce the 4-WC results table verbatim, state the
      10.8% mean champion probability finding, and explain why this vetoed
      the market-matching edit. This is the strongest result in the paper.

6. Simulation and contract pricing (~0.5 page). Source from §8. Cover T
   propagation into the simulator and the structural validation (slot-sum +
   monotonicity checks). Present the 2026 fair-value top-5 from §6.

7. Prediction-market analysis (~1 page). Source from §7. Cover the Kalshi
   data feed, the de-vig methodology, the systematic model-vs-market
   divergence pattern (elite team underpricing), and the honest conclusion:
   this is market favorite-longshot bias against a calibrated model, not
   model error, and it is not tradeable on liquid outrights. Cover the
   arbitrage scanner result (no executable locks). Be direct about the
   negative finding — it is a real result, not a failure.

8. Live paper-trading experiment (~0.5 page). Source from §12.3 and
   trade_log.md for the final numbers. State the hypothesis and rules
   briefly, then present the final summary table (§12.3) and the verdict.
   Do NOT describe individual trades. Frame honestly: a $500 paper experiment
   over one tournament is not sufficient to confirm or reject the
   favorite-fade thesis statistically; state what it does and does not
   establish.

9. Live model validation (~0.5 page). Source from §13.2 and the final
   scorecard log. State the log loss and Brier vs baselines at n=72 and
   interpret. Include the draw under-rating structural note from §13.

10. Limitations and future work (~0.5 page). Source from §9. Include
    regression-dilution correction, un-propagated strength uncertainty,
    knockout-vs-group calibration, and the injury-overlay point. Be honest
    that the hierarchical rebuild was parked because §5.5 showed it wasn't
    needed for calibration, not because it wouldn't improve things.

11. Conclusion (~0.3 page). Restate the three findings: model is well-
    calibrated at match and tournament level; no tradeable edge on liquid
    prediction markets; live experiment result. One sentence on what the
    project demonstrates about the quant loop (measure on resolved data,
    let it veto tempting edits).

**Tables.** Reproduce verbatim from the record: the headline match-model
results table (§6), the 4-WC tournament backtest table (§5.5), and the
§12.3 final trade summary table. Use booktabs formatting.

**What NOT to include.**
- Individual trade settlement descriptions (12.2 entries). The paper gets
  the summary table only.
- Step-by-step script descriptions. Reference script numbers once where
  relevant, then move on.
- The "open questions" list as a list — fold relevant items into §10
  (limitations) as prose.
- This prompt section (§14) of the technical record.

**Citations.** Only cite papers explicitly named in the record: Dixon & Coles
(1997) "Modelling Association Football Scores and Inefficiencies in the
Football Betting Market", and the World Football Elo rating system. Use
\bibitem in a plain thebibliography environment — no BibTeX file needed.

Please output the complete LaTeX source, compilable with pdflatex.
```