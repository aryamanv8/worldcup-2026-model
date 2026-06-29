# Project State & Handoff — worldcup-2026-model

**Living document.** Records the project's current approach + decisions, and serves
as the orientation/handoff for the next working session (including a fresh Claude
conversation). Supersedes `handoff_2026-06-15.md` (delete that file).

**Last updated:** 2026-06-29 (R32 review session: caps/Kelly, advance-market pivot,
arb fee-net, WebSocket plan, collaboration principle).
**Full methods + results:** `docs/technical_record.md` (Strategy v2 is §15).

> **New here? Read in this order:** (1) this §0, (2) §2 standing decisions —
> including §2.0 the collaboration principle, (3) §4 backtest verdict, (4) §6 roadmap,
> (5) §13 file map. Then `docs/strategy_v2.md` and `docs/technical_record.md` §12.4.

---

## 0. WHERE WE ARE RIGHT NOW (2026-06-29) — read first

**Book:** equity **$652.25** (from $500, +30.5%), realized **+$152.25**, **fully
settled** (0 open, 6 closed). Group stage is over; **round of 32 is starting.**

**Sleeve status:**
- **Moneyline** — the validated money-maker. Was **silently broken for knockouts**
  (the R32 market titles `"X vs Y: Regulation Time Moneyline"` defeated the team-name
  parser, so every R32 game was skipped as "unmapped"). **Fixed** 2026-06-28 in
  `01_discover_match_markets.py` (`_clean_team`). Knockout markets are regulation-time
  moneyline = exactly what the model prices, so it's correct once re-run. **Action:
  re-run `morning.sh` to get a real knockout slate.**
- **BTTS** — tiny live experiment (no backtest edge); runs, rarely fires. Fine.
- **Advance/progression** — **GATED OFF.** Its model probs are the frozen June-11 sim,
  now stale (suggested Scotland to reach R16 at 1¢). Script 05 now refuses entries when
  the sim is stale (>2 days) and suppresses high-divergence legs. Revive only after the
  live-advancement recompute (spec in strategy_v2 / technical_record §15).
- **Over/under 1.5** — **shelved.** The scraper's O/U capture hit the H2H stats page,
  not the odds table; the 2 collected values were garbage and have been cleared. Not
  worth more effort (over-1.5 hits ~80%; little room for edge).

**Doc/code note reconciled:** strategy_v2 once implied moneyline would also use the
market-blend correction; it does NOT — moneyline keeps its validated reliable-zone +
3¢ discipline. The correction applies to the new/unvalidated sleeves only.

**Immediate to-dos:** (1) `git commit` on the Mac; (2) re-run `morning.sh` for a
correct knockout moneyline slate; (3) review that slate and place trades as usual.

**Knockout analysis layer (new, analysis-only).** `morning.sh` now also runs:
`24_scan_arbitrage.py` (structural locks on the champion/reach board — runs now),
`32_live_knockout_sim.py` (exact bracket-DP → live reach-round/champion + continent
probs, replacing the stale frozen sim), and `33_cross_market_consistency.py` (market-
internal nesting + live-model-vs-market gaps). The DP and the checks are unit-tested (`--selftest`).

**Bracket COMPLETE + validated (2026-06-29).** `data/processed/knockout_bracket.json`
now holds the full 32-team R32 in bracket order. Seeds were computed from actual
results (`results.csv`); third-place slots assigned via FIFA's official table for the
qualifying combination {B,D,E,F,I,J,K,L}. **All 7 R32 ties already live on Kalshi are
reproduced exactly (incl. all 3 third-place ties), confirming both the seeding and the
FIFA assignment.** So `32_live_knockout_sim.py` now produces real live champion /
reach-round / continent probabilities on the next Mac run, and `33` lights up the
model-vs-market view. (If results ever revise, recompute standings the same way.)

### 2026-06-29 working-session developments (read before trading today)
- **Sizing override (Aryaman's call):** for live discretion he can drop the standing
  caps and size by **quarter-Kelly on full equity**. Full-Kelly was computed and
  rejected (way too aggressive given the model over-claims edge, §4). The standing caps
  in §2 remain the default for automated runs; cap overrides are a per-session human call.
- **Germany NO regulation-fade dropped.** The headline 2026-06-29 R32 slate showed
  Germany NO @ 0.27, claimed +28.5c — a favorite-fade. Removed: it's mostly a **draw
  artifact** ("NO in regulation" pays if Germany draws in 90 then wins in ET), and on
  the clean advance market the model looks wrong (Germany 56% model vs ~93% market).
- **Today's placed-candidate slate (quarter-Kelly):** Netherlands YES @0.43 (~$23.70,
  53 ctr) + Ivory Coast BTTS-NO @0.42 (~$14.43, 33 ctr). Lineup-check first. Full digest:
  `reports/trade_ideas_2026-06-29.md`.
- **Arb scanner now reports NET of fees.** `scripts/24_scan_arbitrage.py` was patched to
  apply Kalshi fees (`ceil(0.07·C·p·(1-p))`) to the dutch-book check. Result on the live
  snapshot: `reach_round_of_16` BUY-ALL-YES nets **+$0.40/unit**; `reach_final` and
  `champion` die on fees. Still snapshot + 32-leg fill risk — needs a live book to act.
- **`morning.sh` BTTS position cap raised 0.02 → 0.05** (so quarter-Kelly governs, not an
  artificial 2% truncation). NOTE: re-runs on 2026-06-29 did not visibly regenerate the
  derived slate — verify the cap actually takes effect (the embedded slate timestamp
  wasn't advancing); may be a stale-output / cp issue worth a look.
- **PIVOT — advance markets are the right knockout surface** (see §6 roadmap item 0).
- **WebSocket live-pricing plan** for accurate niche-market quotes (see §6 roadmap item 0b).

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

**Strategy v2 (adopted 2026-06-24) — full rationale in `docs/strategy_v2.md`.**
The old "favorite-fade / favorite-boost" framing is RETIRED. It was a label on the
single market we traded (per-match win-in-regulation), not a strategy. We now trade
any market the model can price *and* has been shown to calibrate, with every edge
corrected toward the market before we believe it.

### 2.0 COLLABORATION PRINCIPLE — don't settle for a worse method just because you (Claude) can't do the best one yourself

**This is a two-operator project by design (§5): Claude reasons in a sandbox with NO
internet and NO `uv`; Aryaman runs the Mac, which has both, plus a browser and the
ability to download files, run WebSocket/streaming clients, hit authenticated APIs, and
do anything interactive.** When the *best* way to get data or execute an action needs a
capability the sandbox lacks, **do NOT quietly downgrade to an inferior sandbox-only
workaround.** Plan around the split:

1. **Pick the best method first**, then decide who runs which step. If the best source is
   a live WebSocket feed, a login-walled page, a large download, a browser action, or a
   real order — that step is Aryaman's; design for it instead of avoiding it.
2. **Hand Aryaman a precise, runnable artifact** (exact command, script, or steps) and
   say what to send back (a file, a parquet, a JSON, a paste). Then build on what he
   returns.
3. **Name the limitation honestly** ("I can't hold a WebSocket / reach Kalshi / download
   this from here") rather than presenting a degraded result as if it were the best
   available. A stale REST mid is not a substitute for a live order book — say so and
   ask for the better input.
4. **Default to the higher-quality pipeline even if it's more setup.** A one-time Mac-side
   script that produces clean data beats repeatedly reasoning over weak data.

Examples this session: use a Mac-side WebSocket client for live quotes (not REST snapshot
mids); let Aryaman browse/verify current Kalshi API docs; have Aryaman run the model /
fetch / arb execution on the Mac. See §6 roadmap.

Standing rules until real settled results give us reason to revisit:

1. **Model is frozen.** Do not retrain or modify it. Changing it mid-tournament
   destroys the clean live experiment.
2. **Correct before you believe the edge.** No leg trades on raw model edge.
   Blend the model toward the market mid (`paper_trading/scripts/lib_correction.py`,
   default w=0.5) and gate on the *corrected* net edge >= 3c after fees. A leg with
   no market quote to anchor the correction is not tradeable.
3. **Trade only calibrated surfaces.** Moneyline is validated. The goals sleeve
   (totals/BTTS) trades a line ONLY if it passed
   `scripts/30_backtest_derived_calibration.py` (per-market flag in
   `data/processed/derived_calibration.json`). Out of the box that is `over_1.5`
   and `btts`; **`over_2.5` is BLOCKED** (model under-predicts mid-range goals).
   **BTTS P&L backtest (script 31) found no robust edge after vig** (strategy_v2 §9),
   so BTTS runs live only as a **tiny experiment** (`morning.sh`: `--markets btts
   --max-deploy 0.06 --position-cap 0.02`). `over_1.5` calibrated but P&L-untested —
   scraper now also captures O/U odds; backtest it before going live. The
   **progression sleeve (script 05) is turned on as a tiny experiment** too
   (`--max-deploy 0.06 --position-cap 0.02`, champion take-profit-only); it can't be
   backtested (no historical futures odds) and usually finds nothing.
4. **Exit policy by sleeve.** Per-match markets are held to settlement (clean
   attribution). Progression markets (advance / champion) use the rule-based
   take-profit in `05_price_advance_markets.py` — pre-set exit logged at entry, no
   ad-hoc cash-outs.
5. **Keep new position sizes minimal** and treat same-match legs ACROSS sleeves
   (moneyline NO-fav, YES-under, BTTS-NO) as one correlated bet for the deploy cap.
6. **Lineup check before any new position.** Confirm expected XI / no key
   injury-suspension before entering. Human pre-trade filter, not code.
7. **Honest negative results beat optimistic spin.** Record notable findings in
   `technical_record.md` as they happen. (The `over_2.5` block above is exactly
   this rule working.)

> The old rules 2 (hold-everything) and 4 (no-new-fades) are superseded by the
> sleeve-specific exit policy and the calibration/correction gates above.

---

## 3. Current portfolio (source of truth: `paper_trading/portfolio.json`)

**As of 2026-06-29 — book is EMPTY and fully settled.**

| Metric | Value |
|---|---|
| Total equity | **$652.25** |
| Cash | $652.25 |
| Realized P&L | +$152.25 |
| Settled | 6 |
| Open | 0 |

Settled history (6 trades, +$152.25 net): Brazil/Morocco +15.19 (reliable, TIE),
Austria/Jordan −28.67 (fade, LOSS), Mexico/Korea +11.30 (boost, cashout), Turkiye/
Paraguay +93.40 (fade, WIN), Norway/Senegal +17.36 (boost, WIN), Ecuador/Germany
+43.67 (fade, WIN). Full detail in `paper_trading/trade_log.md` (in sync with
`portfolio.json` as of 2026-06-26).

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

## 5. Automation architecture (TWO machines — this is the key design fact)

**Claude's scheduled tasks run in an isolated sandbox that CANNOT run `uv` and
CANNOT reach the internet.** Verified 2026-06-16: `raw.githubusercontent.com`
(match results) and both Kalshi API hosts (`api.kalshi.com`,
`api.elections.kalshi.com`) are proxy-blocked, and `uv` can't download Python.
So **the model + all data fetching MUST run on the Mac**, and the Claude tasks do
**read-and-reason only** over the files the Mac writes. Split:

- **Mac side — `scripts/morning.sh`** (run manually, or via launchd; see below).
  Does the heavy lifting that needs uv + internet: fetch results → settle due
  positions → score model → discover/refresh Kalshi markets → price markets
  (`--show-all`, candidates incl. capped/deferred). Writes everything to
  `reports/daily/<date>/` (portfolio snapshot, `trade_slate.{md,json}`,
  `STATUS.json` marker, `run.log`). Never fails hard.
- **Claude side — two scheduled tasks** (both read-only; both check today's
  `STATUS.json` and tell you to run `morning.sh` if it's missing):
  1. `wc-paper-trading-settlement-loop` (09:09) — reads the settled
     `portfolio.json`, syncs `trade_log.md`, reports settlements.
  2. `wc-trade-ideas-digest` (09:34) — reads the Mac slate + open book, adds the
     reasoning/position-context/lineup layer, writes `reports/trade_ideas_<date>.md`
     and a chat summary (see §11). Surfaces options even when the book is full.

**Hands-free Mac run (recommended):** install the launchd job so `morning.sh`
runs at 07:30 daily, before the Claude tasks read at 09:xx:
```bash
cp scripts/launchd/com.aryamanverma.wc-morning.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aryamanverma.wc-morning.plist
```
Without launchd, just run `./scripts/morning.sh` yourself each morning before
opening Claude. Both Claude tasks only run while the Claude app is open (they catch
up on next launch). **Status (2026-06-16): VERIFIED end-to-end.** `morning.sh` ran
clean on the Mac (5/5 steps ok, no FAILs); both Claude tasks tested via "Run now"
and read the output correctly (today's digest = `reports/trade_ideas_2026-06-16.md`);
launchd job `com.aryamanverma.wc-morning` is installed and queued (exit 0). First
LIVE settlement test is Austria on 2026-06-17 — watch that the settlement task
reports the result and syncs `trade_log.md`. The whole system runs only when the
Mac is awake AND the Claude app is open.

---

## 6. Open threads for the next session (in priority order)

**0. ADVANCE-MARKET PIVOT (new top priority — the right knockout surface).**
Regulation moneyline is the wrong market in knockouts: a draw in 90 mins goes to ET, so
"NO @ favorite in regulation" pays partly on draws — an artifact, not edge (this is why
the 2026-06-29 Germany fade looked fat). Kalshi lists liquid **per-game advance markets**
— series `KXWCROUND-26RO16` ("Will X qualify for R16"), ~90k volume — and we already
discover them (mapped as `reach_round_of_16`/`reach_*`). What's missing is a **calibrated
advancement model**: the live-sim probs (`32_live_knockout_sim.py`) are uncalibrated and
currently misprice (favorites too low — Germany 56% model vs ~93% market). Plan:
  - (a) **Backtest single-game advancement** against historical WC/Euro knockout games
    (win-or-advance incl. ET/pens). Unlike champion futures this IS backtestable — it's a
    binary single-match outcome, same spirit as the moneyline validation (script 29).
  - (b) Wire live-sim advance probs into the advance pricer (`05`) with the market-blend
    correction; gate on the calibration result like the goals sleeve.
  - (c) Only then trade advance markets. Until calibrated, they stay informational.

**0b. LIVE PRICING VIA WEBSOCKET (quote accuracy for niche markets).** Current quotes are
REST snapshot **mids** — for thin advance/derived markets that's far from executable
bid/ask, so those edges are rough. Kalshi has a production WS feed
(`wss://api.elections.kalshi.com/trade-api/ws/v2`; `orderbook_snapshot`/`orderbook_delta`
+ `ticker`/`trade`; RSA-PSS handshake auth). **This is a §2.0 collaboration item:** the
sandbox cannot hold a socket — build a **Mac-side** WS client (Aryaman runs it with his
keys) that maintains live order books and writes `data/processed/live_quotes.parquet`;
the pricer/arb-scanner read that instead of REST mids. Start as a read-only quote logger
(no orders), verify, then point pricing at it.

**0c. ARB EXECUTOR (guarded).** `24_scan_arbitrage.py` now reports net-of-fee dutch books
and found `reach_round_of_16` BUY-ALL-YES at +$0.40/unit on a snapshot. To capture it
safely needs the live book (0b) + a Mac-side executor: all-or-nothing multi-leg fill with
unwind on partials, dry-run by default, `--execute` behind explicit confirmation, Aryaman
holds keys. Do NOT auto-fire.

1. **Firm up the backtest verdict.** Make `scripts/29_backtest_trading_strategy.py` use
   the same model_card Elo-gap stratum gate (n≥30, |Δexp|≤0.05) as the live pricer, re-run,
   and see if the negative-fade / fragile conclusion (§4) holds.
2. **Verify the BTTS cap change actually took effect** (§0 note): `morning.sh` now passes
   `--position-cap 0.05` but the derived slate didn't visibly regenerate on 2026-06-29.
3. **Maintenance:** keep `trade_log.md` / `portfolio.json` in sync as new trades settle;
   bump `technical_record.md` header when verdicts change.

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

## 11. Daily trade-ideas digest (BUILT — updated for Strategy v2)

**Goal (Aryaman's vision, 2026-06-16):** each morning when Claude opens, run the
whole pipeline and produce a ranked list of *potential* trades — fixtures, fresh
Kalshi markets, model fair values, sizing — plus a reasoning layer that weighs
intuition and current-position context. **It should surface candidates even when
the book is full and we don't intend to trade**, purely so we can see the options
and learn. This is an analysis/ideation tool, not an auto-trader.

**v2 update (2026-06-24):** the digest now spans THREE sleeves, not just moneyline.
`morning.sh` runs them all and writes the slates the digest reads:
`trade_slate.*` (moneyline), `derived_slate.*` (totals/BTTS), `advance_slate.*`
(progression + take-profit), plus `derived_calibration.json` (which goals lines are
gated in). Every edge in those slates is already CORRECTED (model blended toward
market); the digest reasons on corrected edges, never raw ones.

### What it should do, each run
1. **Refresh data:** results (`scripts/01_fetch_results.py`), match markets
   (`01_discover_match_markets.py`), outright/advance markets (`22` → `23`). All run
   by `morning.sh`.
2. **Detect what changed:** which markets are NEW or have MOVED since yesterday
   (timestamped snapshots in `paper_trading/data/`). Flag ≥2¢ mid moves / new tickers.
3. **Price + size (all sleeves):** read the three slates `morning.sh` emits —
   moneyline (`02`, `--show-all`), goals (`04`, correction + liquidity/divergence/
   caps), progression (`05`, entries + take-profit). All carry corrected edge,
   quarter-Kelly sizing, fees, and a deferred/suppressed list.
4. **Run the simulator if useful** (`scripts/10_run_simulation.py`) for tournament
   context on the fixtures involved.
5. **Reasoning layer (the part that's more than scripts):** for each candidate,
   add judgment, not just numbers —
   - **trust the suppression flags:** thin-market and large model-vs-market
     divergence legs are SUPPRESSED for a reason (the model is wrong there, not the
     market) — do not resurrect them;
   - **correlation across sleeves:** a moneyline NO-fav, a YES-under, and a BTTS-NO
     on the SAME match are one bet — count them once against the per-position cap;
   - **corrected vs claimed edge:** if `shrunk_by` is large the model disagreed a
     lot with the market; treat the residual edge with extra suspicion;
   - **goals sleeve is gated:** only lines passing `derived_calibration.json`
     (currently `over_1.5`, `btts`; `over_2.5` BLOCKED) may be endorsed;
   - **progression take-profit:** surface any `SELL` flags from `advance_slate`;
   - a lineup-news check (expected XI, injuries/suspensions) before endorsing;
   - the standing rules in §2.
6. **Output:** a dated digest (`reports/trade_ideas_<date>.md`) + a chat summary,
   with two clearly separated buckets, now spanning all three sleeves:
   - **Actionable now** (passes the gate + corrected-edge + liquidity/divergence
     filters AND fits the caps / §2 rules);
   - **Informational only** (real candidates we are NOT placing — capped/deferred,
     suppressed, blocked line, or sub-threshold) — shown *with the reason* it's
     parked. This is the "let me see options anyway" bucket Aryaman asked for.

### Execution environment — RESOLVED + VERIFIED 2026-06-16
The sandbox cannot run uv or reach results/Kalshi (verified — see §5). So we use
the **Mac-side `scripts/morning.sh` writes outputs → Claude tasks read + reason**
architecture (option (c)+ hybrid). `morning.sh`, the launchd plist, and both
read-only Claude tasks are built, run end-to-end clean, and launchd is installed.
The pipeline is live. Remaining refinement (optional, not blocking): tune the
digest's reasoning/formatting against more real slates as the tournament runs.

### Other open design decisions
- **Merge or separate?** Currently kept as two read-only Claude tasks (settlement
  09:09 + digest 09:34). Could later merge into one morning routine if two firings
  feels redundant — both just read the same `morning.sh` output.
- **Trigger:** daily ~8–9am while the app is open (matches the settlement task), or
  ad-hoc "run now" each morning.
- **Market-movement threshold:** define what counts as "odds updated" worth
  flagging (e.g. ≥2¢ mid move, or any new ticker).

### Guardrails (do not drift)
The digest must respect §2 (v2 rules): it can *show* suppressed, blocked, capped, or
divergent ideas, but must label them informational and never present a suppressed
leg, a blocked goals line (e.g. over_2.5), or a cap-busting add as recommended.
Honest framing over a long idea list. The correction is not optional — an edge is
only real after blending toward the market.

## 12. Session prompt (for a fresh Claude conversation)

> You're picking up a Python + data-science project, worldcup-2026-model
> (~/Projects/worldcup-2026-model). Read `CLAUDE.md`, then `docs/handoff.md` (§0, §2
> incl. §2.0 collaboration principle, §4, §6, §13) and `docs/technical_record.md`
> §12.4. Scripts run with `uv run python` from the repo root, **on the Mac** — your
> sandbox has no internet and no `uv`, so follow §2.0: for anything needing live data,
> a browser, downloads, a WebSocket, or order execution, hand me a runnable
> command/script and build on what I send back rather than settling for a weaker
> sandbox-only method. Honor the §2 standing decisions (model frozen; correct every
> edge toward the market; trade only calibrated/gated surfaces; sleeve-specific exit
> policy; correlation-grouped caps; lineup check first). Tell me what's settled since
> the last handoff date, then propose next steps from §6 (top priority: the
> advance-market pivot + calibration) before doing anything.

---

## 13. File map — where to look to understand each part

**Orientation / decisions**
- `CLAUDE.md` — short project instructions, auto-loaded by a fresh conversation.
- `docs/handoff.md` — THIS file; living state, standing decisions, roadmap.
- `docs/strategy_v2.md` — full rationale for the multi-sleeve / correction strategy.
- `docs/technical_record.md` — methods + results; §12.4 backtest verdict, §15 Strategy v2.

**Stage 1 — the model (frozen)**
- `src/` + training scripts 04–10, 17, 20–21, 25 (DO NOT re-run; no-ops mid-tournament).
- `data/processed/backtest_predictions_recalibrated.parquet` — frozen model preds.

**Stage 2/3 — pricing, sleeves, paper trading**
- `paper_trading/scripts/01_discover_match_markets.py` — Kalshi match-market discovery.
- `paper_trading/scripts/02_price_match_markets.py` — moneyline pricer (validated sleeve).
- `paper_trading/scripts/04_price_derived_markets.py` — goals/BTTS sleeve (corrected).
- `paper_trading/scripts/05_price_advance_markets.py` — progression/advance sleeve (gated).
- `paper_trading/scripts/lib_correction.py` — market-blend correction (w=0.5).
- `paper_trading/portfolio.json` — source of truth for the book; `trade_log.md` — human log.
- `scripts/29_backtest_trading_strategy.py` — strategy backtest engine (§4 verdict).
- `scripts/30_backtest_derived_calibration.py` — per-line calibration gate.

**Knockout analysis layer**
- `scripts/22_kalshi_discover.py` / `23_map_model_vs_market.py` — outright/advance discovery + mapping.
- `scripts/24_scan_arbitrage.py` — structural arb scan (now NET of fees).
- `scripts/32_live_knockout_sim.py` — exact bracket-DP → live reach/champion probs.
- `scripts/33_cross_market_consistency.py` — nesting + live-model-vs-market gaps.
- `data/processed/knockout_bracket.json` — full 32-team R32 (complete + validated).

**Automation (two-machine, see §5)**
- `scripts/morning.sh` — the Mac-side pipeline; writes `reports/daily/<date>/`.
- Claude scheduled tasks (read-only): settlement loop + trade-ideas digest (§11).
- Output per day: `reports/daily/<date>/{STATUS.json,trade_slate.*,derived_slate.*,advance_slate.*,run.log}`
  and `reports/trade_ideas_<date>.md`.

**Roadmap stubs to build (see §6, all Mac-side):** advance-market backtest/calibration,
`live_quotes.parquet` WebSocket logger, guarded arb executor.
