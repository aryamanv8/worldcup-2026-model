# Strategy v2 — corrected, multi-sleeve trading

**Status:** adopted 2026-06-24. Supersedes the favorite-fade/boost operating rules
in `handoff.md §2`. The forecasting model is unchanged and still frozen; this
document changes only the *trading layer* on top of it.

**One-line summary:** stop organizing the book around "fade vs boost," correct
every model probability toward the market before believing its edge, and trade any
market the model can actually price and has been shown to calibrate — starting with
goals markets (totals, BTTS) and tournament-progression markets, where the model is
most differentiated.

---

## 1. Why the old framing is retired

"Favorite-fade" and "favorite-boost" were never a strategy — they were labels on
the only surface we traded (per-match win-in-regulation). Two findings forced the
rethink:

1. **The model is now validated as a forecaster.** The live 2026 scorecard climbed
   from below the flat baseline (June 15) to clearly beating both baselines by June
   24: mean log loss 0.938 vs flat 1.099 and base-rate 1.009; top-pick accuracy
   0.375 → 0.61; binary Brier 0.226 → 0.188. Whatever we change, it is *not* the
   model.

2. **Raw model edge is fiction; corrected edge is the real quantity.** The
   strategy backtest claimed ~14c mean edge but realized 43% wins, and the live
   calibration table shows the model over-states the unlikely tail
   (model_p (0,0.4] → realized ~0.23). The 3c gate was firing exactly where the
   model disagreed most with the market — i.e. where the market was right. So the
   problem was never "which direction"; it was that we trusted the uncorrected
   model.

The fix is structural, not directional: **shrink toward the market, then trade
wherever a real corrected edge survives.**

---

## 2. The correction layer (gates everything)

Implemented in `paper_trading/scripts/lib_correction.py` (pure numpy, self-tested).

- **Market anchor.** From the two Kalshi asks, recover a clean market probability
  via the YES bid/ask midpoint: `yes_mid = (yes_ask + (1 − no_ask)) / 2`.
- **Blend.** Corrected fair value `fv = w·model + (1−w)·market`, default `w = 0.5`
  (trust model and market equally). `w` is a single honest knob: lower = trust the
  market more.
- **Edge.** Net edge is computed against `fv`, never the raw model:
  `edge = fv − ask − fee_per_contract`. The pricer logs both `raw_edge` and
  corrected `edge` and `shrunk_by`, so we can see how much fictional edge the
  correction removed on each leg.
- **Tuning `w`.** Once enough settled, quoted legs exist (model fv, market mid at
  entry, win/lose), `fit_blend_weight()` picks the `w` that minimizes live log
  loss. Until then, `w = 0.5` is the prior. A fitted `w < 0.5` would confirm the
  market deserves more weight than the model — which the backtest already implies.

**Rule:** no leg is tradeable without a usable market quote to anchor the
correction. We do not trade where we cannot correct.

---

## 3. Market sleeves — what the model can price, and the plan for each

The engine emits a full joint scoreline matrix per match and a 50k-path tournament
simulation, so its native outputs are richer than the one surface we've used.

| Sleeve | Source | Status | Plan |
|---|---|---|---|
| Moneyline (win in reg.) | score matrix W/D/L | live, validated | Keeps its **reliable-zone + 3¢** discipline (NOT the market-blend correction — that's for the unvalidated sleeves). It made +$152 live on this logic; don't change a working sleeve mid-tournament. |
| **Totals (over/under goals)** | `total_over_prob(grid, line)` | **new** | Highest-value: it's literally a goals model and Kalshi `KXWCTOTAL` lines are liquid. **Gated on §4 calibration backtest passing.** |
| **BTTS (both teams to score)** | `btts_prob(grid)` | **new** | Same gate as totals. `KXWCBTTS` markets exist and are liquid. |
| **Advance / make-knockouts** | `tournament_probs.parquet` | **new** | Price team-to-advance and round-reached vs market; less efficient than the headline winner market. |
| Outright winner | `tournament_probs.parquet` | analysed | Stage 2 found **no value edge** (favorite-longshot bias is market structure). Do **not** treat as a value play — use only as the take-profit vehicle (§5). |
| Spread / Asian handicap | `spread_prob(grid, line)` | helper ready | Defer until totals/BTTS validate; same calibration question. |
| Parlays | joint score matrix | deferred | High risk — multiplies miscalibration. Only ever as same-match correlated legs priced off the joint matrix, capped tiny, after §4. |
| Player / event props | — | **out** | No player-level model and no data feed. Not pursued this tournament. |

---

## 4. Honest gate before any new sleeve goes live

The W/D/L surface was validated by the tournament backtest; **totals and BTTS were
never scored**, so they are not yet allowed to trade real (paper) size. Before the
derived sleeve opens:

`scripts/30_backtest_derived_calibration.py` scores model totals and BTTS
predictions against the ~25k-match history — reliability bins (predicted vs
realized) and log loss vs an over-rate / base-rate baseline. The sleeve goes live
only if the model beats the baseline and the reliability bins are roughly diagonal.
If it doesn't calibrate, we don't trade it — same discipline that produced the
"no edge on liquid outrights" result in Stage 2.

---

## 5. Take-profit policy (new — only for progression markets)

Per-match markets are still **held to settlement** for clean attribution. But
advance/winner markets are continuous and our edge there is largest pre-tournament
and *decays as results arrive*, so harvesting that decay is the strategy, not a
deviation:

- Enter a team-to-advance / winner position only with corrected edge ≥ gate.
- Set a **take-profit target** at entry: sell when the market price reaches the
  corrected fair value (edge fully realized) **or** rises by a pre-set multiple of
  the entry stake, whichever comes first. The exit, target, and reason are logged
  at entry so the exit is rule-based, not discretionary.
- This is explicitly separate from the per-match "hold to settlement" rule, and
  positions opened under it are tagged `progression` so attribution stays clean.

> Note: the Mexico early cash-out (+$11.30) was an unplanned exit under the old
> rules. Under v2 it would have been either disallowed (per-match) or pre-planned
> (progression). No more ad-hoc exits.

---

## 9. BTTS backtest result + decision (2026-06-24)

`scripts/31_backtest_derived_strategy.py` was run on 97/128 WC 2018/2022 matches with
real BetExplorer BTTS closing odds (scraped via `scripts/fetch_goals_odds.py`).
**Honest result: no robust edge after the bookmaker margin.** With realistic vig and
the default correction (w=0.5), the strategy qualifies only ~2 bets across two World
Cups — it essentially doesn't fire. A real sample appears only when we lean on the
raw, uncorrected model:

| trust in model | bets | win | ROI (with vig) |
|---|---|---|---|
| 50/50 (w=0.5, our default) | 2 | 100% | +188% (noise, n=2) |
| model-leaning (w=0.75) | 8 | 50% | +57% |
| raw model, no correction (w=1.0) | 23 | 48% | +20% |

BTTS is near a coin-flip; once you pay the vig, the model's calibration edge mostly
evaporates unless we trust the (over-confident) raw model — which we corrected away on
purpose. This is the same "looks good but fragile / small-sample" pattern as the
moneyline backtest. Caveats: BTTS only (over_1.5 odds unarchived), 97/128 matches,
rho placeholder on the off-Mac run.

**Decision (Aryaman, 2026-06-24): run BTTS as a TINY LIVE EXPERIMENT anyway** — the
backtest didn't condemn it (no evidence it loses), so pay a small amount to gather
forward 2026 evidence. Operationalized in `morning.sh`: derived sleeve restricted to
`--markets btts`, sized `--max-deploy 0.06 --position-cap 0.02` (≈6% of bankroll total,
≈2% per bet), corrected edge + all guards still required. Revisit after a dozen-ish
live settlements; turn off if it underperforms.

**Over/under 1.5 (in progress, 2026-06-24).** Passes the calibration gate but was
never P&L-tested (odds unarchived). `scripts/fetch_goals_odds.py` was extended to also
capture the Over/Under tab and parse the 1.5 line (with raw-capture fallback, since
O/U layouts are finicky). Once `over15/under15` are filled in `wc_goals_odds.csv`,
re-run `scripts/31_backtest_derived_strategy.py` — it already prices `over_1.5`. Expect
a lopsided market (over-1.5 is usually 75–85% likely); edge after vig is unlikely but
worth measuring. Not live until backtested.

**Progression sleeve — GATED OFF (2026-06-28 review).** The live run on 2026-06-28
exposed the flaw: its model probabilities come from the **frozen pre-tournament sim**
(`tournament_probs.parquet`, dated 2026-06-11). As teams are eliminated those probs go
stale — it suggested **Scotland to reach R16 at a 1¢ market** (model 21% vs market 1%),
a fake edge on a team that's essentially out. Fixes applied to `05_price_advance_markets.py`:
a **staleness gate** (refuses new entries when the sim is >2 days old — it always is now)
and a **divergence guard** (suppress |model−market| > 0.12). So the sleeve is safe but
effectively off for entries; it still monitors take-profit on any held position.

*Path to revive (knockout-rollforward recompute — not yet built):* the group stage is
over, so the fix is NOT re-simulating groups. Take the **actual R32 bracket** (the
fixtures are already in the Kalshi feed, e.g. South Africa–Canada, Brazil–Japan, …) and
roll it forward with the frozen *match* model (`simulate_knockout_match` repeated),
aggregating reach-round / champion probabilities. Write to `tournament_probs.parquet`,
then re-run 23 → 05. Eliminated teams then correctly show ~0%. Deferred deliberately:
it needs the live bracket + a Mac run to verify, and this sleeve had no validated edge
anyway (Stage 2). Build it as a focused, verified task if/when the sleeve is wanted.

**Over/under 1.5 — SHELVED (2026-06-28).** The scraper's "O/U tab" click landed on the
head-to-head *stats* page, not the odds table, so no real over/under odds were collected
(the 2 stray values were garbage and have been cleared from `wc_goals_odds.csv`). over-1.5
hits ~80% of matches, leaving little room for edge after vig, so this isn't worth more
scraping effort. BTTS remains the only live goals experiment.

**Moneyline knockout fix (2026-06-28).** R32 market titles are
`"<A> vs <B>: Regulation Time Moneyline"`; the team parser was reading team B as
`"Canada: Regulation Time Moneyline"` and skipping every knockout match. Fixed in
`01_discover_match_markets.py` (`_clean_team`). Knockout markets settle on the
regulation winner — exactly the model's W/D/L — so no other change is needed.

---

## 6. Sizing and risk (revised 2026-06-24)

Conviction is expressed by **quarter-Kelly on the corrected edge** — a bigger,
better-corrected edge already sizes the bet up automatically, so "make the trade if
we believe in it" is built in. We do not need an arbitrary low total cap fighting
that. Revised policy:

- **Quarter-Kelly** on the corrected edge, fee-aware (`scripts/26_fee_model.py`). Unchanged.
- **Per-position cap: 10% of bankroll**, enforced on **correlation groups** — a
  moneyline NO-fav, a YES-under, and a BTTS-NO on the *same match* are ONE position,
  capped together. This is the real risk control (stops stacking correlated legs).
- **Total deploy cap: 50% of bankroll** (raised from 20%). High enough to act on
  genuine conviction across several uncorrelated games, low enough to never bet the
  experiment into a hole on a correlated cluster. Configurable via `--max-deploy`
  (set toward `1.0` for effectively "no cap" — not recommended while the goals
  sleeve is P&L-unvalidated).
- **Liquidity floor** (`--min-volume`, default 500 contracts): skip markets too thin
  to trust (e.g. Curaçao vs Ivory Coast traded 3 contracts/24h on 2026-06-24).
- **Max-divergence guard** (`--max-divergence`, default 0.25): if the model and the
  market disagree by more than this, SUPPRESS the leg. A huge gap vs a liquid quote
  means the model is wrong, not that there's edge — the blend alone leaves too much
  fictional edge (the Colombia/Congo-DR BTTS case: model 44% vs liquid market 10%).

> Why not remove the total cap entirely (Aryaman's question, 2026-06-24): with the
> correction imperfect and the goals sleeve not yet P&L-backtested, uncapped
> exposure on correlated paper bets risks ruin and muddies attribution. Quarter-Kelly
> + the per-position cap already let conviction size up; a 50% ceiling is the safety
> belt, not a straitjacket. Revisit once script 31 shows the sleeve makes money.

---

## 7. What did NOT change

- The model is frozen. No retraining mid-tournament.
- Quarter-Kelly, caps, fee model, reliable-zone definition for moneyline.
- Honest-negative-results discipline: if a sleeve doesn't calibrate or corrected
  edge disappears, we record that and don't trade it.

---

## 8. Build status (2026-06-24)

| Piece | File | State |
|---|---|---|
| Correction layer | `paper_trading/scripts/lib_correction.py` | built + self-tested |
| Derived calibration backtest | `scripts/30_backtest_derived_calibration.py` | built — **run on Mac to open the sleeve** |
| Totals/BTTS pricer | `paper_trading/scripts/04_price_derived_markets.py` | built — run on Mac; now with liquidity/divergence/cap guards |
| Advance pricer + take-profit | `paper_trading/scripts/05_price_advance_markets.py` | built — run on Mac |
| Goals-sleeve P&L backtest | `scripts/31_backtest_derived_strategy.py` | built — **needs `data/raw/wc_goals_odds.csv` (WC totals/BTTS closing odds)** before it can run |
| Morning pipeline | `scripts/morning.sh` | wired: runs 30 → 04 → 22/23 → 05 and collects all slates |

All model-running scripts execute on the Mac (the Claude sandbox has no model
runtime or network, per `handoff.md §5`). Next Mac run: `morning.sh`, then the two
new pricers; review the calibration backtest output before enabling the derived
sleeve in `morning.sh`.
