# CLAUDE.md — worldcup-2026-model

Project instructions for any Claude conversation working in this repo. Read this first,
then `docs/handoff.md`.

## What this is
Aryaman Verma's WC-2026 quant project: a frozen Poisson/Dixon-Coles match model used as
fair-value vs Kalshi prediction markets, with a live **$500 paper-trading** experiment
(now ~$652). Three sleeves: moneyline (validated), goals/BTTS (calibrated, tiny), and
progression/advance (gated, being rebuilt). Full state + decisions live in
`docs/handoff.md`; methods in `docs/technical_record.md`; strategy in `docs/strategy_v2.md`.

## Read-first order
1. `docs/handoff.md` §0 (current state), §2 (standing decisions, incl. §2.0 below),
   §4 (backtest verdict), §6 (roadmap), §13 (file map).
2. `docs/technical_record.md` §12.4 (why the edge is NOT bankable) and §15.
3. `docs/strategy_v2.md`.

## Two-machine architecture — non-negotiable
- **Claude runs in a sandbox with NO internet and NO `uv`.** It cannot reach Kalshi /
  results APIs, cannot run the model/pricer/fetch, cannot hold a WebSocket, cannot
  download files, cannot push git.
- **The Mac (Aryaman) has internet, `uv`, a browser, downloads, streaming clients, and
  the keys.** It runs `scripts/morning.sh`, which writes `reports/daily/<date>/`. Claude
  **reads those files and adds the reasoning layer.**

## §2.0 COLLABORATION PRINCIPLE — do not settle for a worse method
When the *best* way to get data or do an action needs a capability the sandbox lacks
(live feed, login-walled page, large download, WebSocket, browser action, real order),
**do not quietly downgrade to an inferior sandbox-only workaround.** Instead:
1. Choose the best method first, then split the work by who can run it.
2. Hand Aryaman a precise, runnable command/script and say exactly what file to send back;
   build on what he returns.
3. Name the limitation honestly ("I can't hold a WebSocket / reach Kalshi from here")
   rather than passing off a degraded result (e.g. a stale REST mid) as the best available.
4. Prefer the higher-quality pipeline even if it's more one-time setup.
(Full version + examples: `docs/handoff.md` §2.0.)

## Standing trading rules (handoff §2)
Model frozen · correct every edge toward the market before believing it · trade only
calibrated/gated surfaces (`over_2.5` BLOCKED) · per-match held to settlement, advance
uses rule-based take-profit · minimal sizing, correlation-grouped caps · **lineup check
before any new position** · honest negatives over optimistic spin. Caps may be overridden
to Kelly sizing only as an explicit per-session call by Aryaman.

## Don't
Retrain/modify the model · run training scripts 04–10/17/20–21/25 · place trades, move
money, or auto-fire orders on Aryaman's behalf · present suppressed/blocked/cap-busting
ideas as recommended.
