# Project State & Handoff — worldcup-2026-model

**Living document.** Records the project's current approach + decisions, and serves
as the orientation/handoff for the next working session (including a fresh Claude
conversation). Supersedes `handoff_2026-06-15.md` (delete that file).

**Last updated:** 2026-06-16 (after the historical strategy backtest).
**Full methods + results:** `docs/technical_record.md` (backtest verdict is §12.4).

---

## 1. What this project is (30-second version)

Three-stage project by Aryaman Verma (CMU, applied math + computational finance):

- **Stage 1** — calibrated Poisson + Dixon-Coles match model for WC 2026, trained
  on ~25k international matches (2000–2026), Elo + squad value + form features,
  single temperature T=0.77. **Frozen for the tournament.**
- **Stage 2** — model as a fair-value reference vs Kalshi prediction markets.
  Finding: no tradeable edge on liquid outrights.
- **Stage 3** — live $500 paper-trading experiment on per-match Kalshi markets.
  Quarter-Kelly sizing, 10% per-position cap, 20% max deployment, entry requires
  reliable Elo zone AND ≥3¢ net edge after fees.

Repo: `github.com/aryamanv8/worldcup-2026-model`.

---

## 2. CURRENT APPROACH & STANDING DECISIONS (read this before acting)

These are settled. Treat them as the operating rules until real settled results
give us a reason to revisit:

1. **Model is frozen.** Do not retrain or modify it. Changing it mid-tournament
   destroys the clean live experiment.
2. **Hold all open positions to settlement.** No hedging, no early exit —
   attribution requires it.
3. **Keep any new position sizes minimal.** The backtest did not earn the right to
   bet bigger (see §4).
4. **Add NO new favorite-fade trades.** That is the one style the backtest actively
   warns against, and the current book is already fully concentrated in it.
5. **Lineup check before any new position.** Confirm expected XI / no key
   injury-suspension before entering. This is a human pre-trade filter, not code.
6. **Honest negative results beat optimistic spin.** Record notable findings in
   `technical_record.md` as they happen.

---

## 3. Current portfolio (source of truth: `paper_trading/portfolio.json`)

| Metric | Value |
|---|---|
| Total equity | **$515.19** |
| Cash | $416.59 |
| Realized P&L | +$15.19 |
| Settled | 1 (WIN — Brazil/Morocco) |
| Open | 3 |

Open positions (all `favorite-fade`, i.e. one correlated bet, not three):

| Fixture | Bet | Settles |
|---|---|---|
| Austria vs Jordan | NO @ Austria | **2026-06-17** |
| Turkiye vs Paraguay | YES @ Paraguay | 2026-06-19 |
| Ecuador vs Germany | NO @ Germany | 2026-06-25 |

`portfolio.json` and `paper_trading/trade_log.md` were in sync as of 2026-06-16.

---

## 4. What we learned from the backtest (the new, load-bearing finding)

We finally tested the *trading strategy* (not just the forecasting model) against
2018 + 2022 World Cup group games, using real closing-ish odds (BetExplorer
average-final) in `data/raw/wc_closing_odds.csv` via `scripts/29_backtest_trading_strategy.py`.

**Headline:** +$330 / +26% ROI on staked, 43% win rate over 42 trades.
**But the verdict is: NOT a robust or bankable edge, and it does not validate the
live book.** Three reasons:

1. **Fragile.** Switch the reliable-zone definition (symmetric `|elo|≤150` vs the
   signed `(−50,150)`) and the total drops to +$65/+8% AND the driver flips
   (favorite-boost vs favorite-fade). Per-trade Sharpe ≈ 0 either way → noise.
2. **Our live thesis lost.** Favorite-fade — the basis of all 3 open positions —
   lost 8% (33% win) under the primary zone. The profit came entirely from
   favorite-*boost* (the opposite trade).
3. **Model over-claims edge.** ~14¢ mean *claimed* edge but only 43% realized win
   rate. The 3¢ gate fires where the model most disagrees with the market, and
   history says the market was closer to right there.

Full detail, tables, and caveats: `technical_record.md` §12.4.

---

## 5. Automated maintenance — already running

A scheduled task ("wc-paper-trading-settlement-loop", daily ~9am) runs the
settlement loop automatically: fetch results → settle any due position →
sync `trade_log.md` → update the live scorecard → report. It covers Austria
(6/17), Turkiye/Paraguay (6/19), Germany/Ecuador (6/25). It only runs while the
Claude app is open (catches up on next launch). Manage/disable it in the Scheduled
sidebar.

Manual equivalent (run on the Mac, where `uv` + network work):
```bash
cd ~/Projects/worldcup-2026-model
uv run python scripts/01_fetch_results.py
uv run python paper_trading/scripts/03_settle.py
uv run python scripts/28_score_live_predictions.py
# then manually sync paper_trading/trade_log.md to portfolio.json
```

---

## 6. Open threads for the next session (in priority order)

0. **BUILD THE DAILY TRADE-IDEAS DIGEST (new top priority — full spec in §11).**
   A morning routine that runs the whole pipeline and outputs a ranked list of
   candidate trades with sizing + reasoning, including options we won't act on.
1. **Firm up the backtest verdict.** The backtest uses a raw Elo-window reliable
   zone; the *live* pricer (`paper_trading/scripts/02_price_match_markets.py`) uses
   the richer model_card Elo-gap stratum gate (n≥30, |Δexp|≤0.05). Make script 29
   use the same gate, re-run, and see if the negative-fade / fragile conclusion
   holds. This is the single best way to trust or soften the verdict.
2. **Conservative Phase 3 scan** (after Austria settles frees deployment room).
   Re-run `paper_trading/scripts/02_price_match_markets.py`; apply §2 rules —
   minimal sizing, NO new favorite-fade, lineup check first. Favorite-boost
   candidates are the only direction the data (weakly) supports.
3. **After all 3 open positions settle:** update `trade_log.md` §12.2 + §12.3
   summary, write the narrative verdict, bump `technical_record.md` header date.

---

## 7. Environment / engineering notes

- **Run scripts on the Mac with `uv run python`.** In the Cowork sandbox, `uv`
  cannot run (it tries to re-download Python and the sandbox network is
  allowlisted/proxy-blocked). System Python in the sandbox can read parquet/CSV but
  not run the `wc2026` package scripts.
- **Git `index.lock` issue:** the sandbox can't manage git locks on the macOS APFS
  mount, and can't auth to GitHub. **Commit + push from the Mac terminal.** If you
  hit `Unable to create index.lock: File exists`, close any editor git integration
  and `rm -f .git/index.lock`, then retry.
- **Sandbox can't delete files on the Mac drive** (APFS-from-Linux). Stray files
  Claude can't remove get marked or noted; delete them from the Mac.

---

## 8. Naming conventions (do not cross-apply)

- Model / results / backtest side (martj42): "Turkey", "Iran", "Czech Republic",
  "DR Congo", "United States", "South Korea".
- Kalshi / paper-trading side: "Turkiye", "IR Iran", "Czechia", "Congo DR", "USA".
- `scripts/29` crosswalks common odds-source variants automatically and prints any
  it can't match.

---

## 9. Key files

- `paper_trading/portfolio.json` — source of truth for paper trading.
- `paper_trading/trade_log.md` — human-readable log (sync manually to portfolio).
- `scripts/29_backtest_trading_strategy.py` — strategy backtest engine.
- `data/raw/wc_closing_odds.csv` — 2018/2022 historical odds (BetExplorer).
- `reports/backtest_strategy_*.md|csv` — backtest output (latest is canonical).
- `data/processed/backtest_predictions_recalibrated.parquet` — frozen model preds
  (schema: `p_home_win/p_draw/p_away_win`, `elo_diff`/`home_elo`/`away_elo` baked in).
- `docs/technical_record.md` — full methods, decisions, §12.4 backtest verdict,
  §14 LaTeX paper prompt.

---

## 10. What NOT to do

- Don't retrain or modify the model (frozen).
- Don't hedge or early-exit the open positions (hold to settlement).
- Don't add more favorite-fade trades.
- Don't enter any new position without a lineup check.
- Don't scale sizing up off the back of this backtest — it's noise-level.
- Don't run training scripts 04–10, 17, 20–21, 25 (no-op, confusing).

---

## 11. Planned build — daily trade-ideas digest (NOT yet built)

**Goal (Aryaman's vision, 2026-06-16):** each morning when Claude opens, run the
whole pipeline and produce a ranked list of *potential* trades — fixtures, fresh
Kalshi markets, model fair values, sizing — plus a reasoning layer that weighs
intuition and current-position context. **It should surface candidates even when
the book is full and we don't intend to trade**, purely so we can see the options
and learn. This is an analysis/ideation tool, not an auto-trader.

### What it should do, each run
1. **Refresh data:** latest results/fixtures (`scripts/01_fetch_results.py`) and the
   live Kalshi match markets (`paper_trading/scripts/01_discover_match_markets.py`).
2. **Detect what changed:** which markets are NEW or have MOVED since yesterday.
   `paper_trading/data/` already stores timestamped snapshots
   (`match_markets_<ts>.json`) — diff today's vs the last to flag new/updated lines.
3. **Price + size:** run `paper_trading/scripts/02_price_match_markets.py`, which
   already emits a trade slate with model FV, net edge, quarter-Kelly sizing, fees,
   and a deferred list. Run it in "show everything" mode so capped/deferred and
   out-of-zone candidates still appear (it has `--show-all` and `--max-deploy`).
4. **Run the simulator if useful** (`scripts/10_run_simulation.py`) for tournament
   context on the fixtures involved.
5. **Reasoning layer (the part that's more than scripts):** for each candidate,
   add judgment, not just numbers —
   - correlation vs the current open book (flag if it doubles up the existing
     all-favorite-fade concentration);
   - the backtest context (§4): favorite-fade is weak/negative, favorite-boost is
     the only weakly-supported direction, the model over-claims edge ~14¢;
   - a lineup-news check (expected XI, injuries/suspensions) before endorsing;
   - the standing rules in §2.
6. **Output:** a dated digest (`reports/trade_ideas_<date>.md`) + a chat summary,
   with two clearly separated buckets:
   - **Actionable now** (passes filters AND fits the book / caps / §2 rules);
   - **Informational only** (real candidates we are NOT placing — full book,
     favorite-fade, out-of-zone, or sub-threshold) — shown *with the reason* it's
     parked. This is the "let me see options anyway" bucket Aryaman asked for.

### Open design decisions for the next session to resolve FIRST
- **Execution environment (the blocker to settle).** These scripts need
  `uv run python` with the project venv + the `wc2026` package + the model pickle.
  In the Cowork sandbox, `uv` cannot run (network-blocked Python download), and
  bash runs in the Linux sandbox, not on the Mac — so a scheduled task likely
  **cannot run the model itself**. Realistic options to choose between:
  (a) **Hybrid** — Aryaman runs the scripts on the Mac (or a tiny `make morning`
      wrapper), pastes/loads the slate, and Claude does the reasoning + digest;
  (b) **Sandbox-native** — get the scripts running under system Python in the
      sandbox (`pip install --break-system-packages` the deps, `PYTHONPATH=src`,
      no uv) so a scheduled task can run end-to-end — feasible but needs a port
      of the run path and dependency list, and must read the mounted Mac repo;
  (c) **Mac-side automation** — a cron/launchd job on the Mac writes the daily
      slate to `reports/`, and the morning Claude session reads + reasons over it.
  Note the existing settlement scheduled task has the SAME constraint — verify it
  can actually execute `uv run` in the scheduled environment; if not, it needs the
  same hybrid treatment. **Resolve this before building.**
- **Merge or separate?** This likely combines with the existing
  "wc-paper-trading-settlement-loop" task into one morning routine
  (settle → refresh markets → trade ideas → digest), rather than two tasks.
- **Trigger:** daily ~8–9am while the app is open (matches the settlement task), or
  ad-hoc "run now" each morning.
- **Market-movement threshold:** define what counts as "odds updated" worth
  flagging (e.g. ≥2¢ mid move, or any new ticker).

### Guardrails (do not drift)
The digest must respect §2: it can *show* favorite-fade and full-book ideas, but it
must label them informational and must never present scaling-up or new fades as
recommended. Honest framing over a long idea list.

## 12. Session prompt (for a fresh Claude conversation)

> You're picking up a Python + data-science project, worldcup-2026-model
> (~/Projects/worldcup-2026-model). Read `docs/handoff.md` and `docs/technical_record.md`
> §12.4 first. Scripts run with `uv run python` from the repo root, on the Mac.
> Honor the standing decisions in handoff §2 (model frozen; hold positions to
> settlement; minimal sizing; no new favorite-fade; lineup check first).
> Tell me what's settled since 2026-06-16. The likely headline task is building the
> daily trade-ideas digest (handoff §11) — start by resolving its "execution
> environment" design decision with me before writing code. Then propose next steps
> from handoff §6 before doing anything.
