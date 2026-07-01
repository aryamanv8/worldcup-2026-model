# Decision log — worldcup-2026-model

Append-only record of **material decisions and structural changes**, newest first. One
entry per change: what, why, files touched, status. This is the single place a change
gets recorded — the other docs (`handoff.md` state, `technical_record.md` methods,
`strategy_v2.md` strategy) describe the *current* system; this file records *how it got
that way* so decisions stop getting lost or silently contradicted.

Convention: `YYYY-MM-DD — [ID] Title` — ID matches `docs/architecture_audit.md` findings
(F1–F7) where applicable.

---

## 2026-07-01 — [F3] OPEN DECISION: frozen strength vs knockout form-refresh
**Status: UNRESOLVED — gates all tier-B edge work.**
The model and bracket are live (they know who advanced), but team *strength* is frozen at
pre-tournament June values by design (`team_features.parquet` + model frozen for the
tournament). Consequence, now visible on the newly-mapped reach markets: the live sim
disagrees with the market by huge, one-directional margins (2026-07-01 cross-market check:
France reach-QF 33% model vs 88% market, −55 pts; Morocco −50; USA −40). This is almost
certainly the frozen model being wrong (market has group-stage info we don't), not edge.
**The fork:** (a) accept frozen strength and only trade where corrected edge survives, or
(b) build a controlled knockout strength-refresh (bounded update from group-stage results,
re-validated). Do not trade any tier-B surface until this is decided. Owner: Aryaman.

## 2026-07-01 — [F2] Unified market discovery + canonical market map
**Status: DONE + committed (2e7682b).**
Replaced two partial discoverers (script 22 probed a *guessed* series list; paper-trading
01 kept only already-priceable per-match types) with one exhaustive, self-refreshing
inventory. **Why:** neither could answer "are we seeing all the markets?" — we were seeing
~5 of 77 live series.
- NEW `scripts/34_market_inventory.py` — discovers the full Kalshi catalog three ways
  (series-pattern + open-events title scan + seeds), pulls every market unfiltered, and
  classifies each series against a hand-verified map. Flags any unmapped series as
  `UNKNOWN — review` so new families can't be silently missed.
- NEW `data/reference/wc_market_map.csv` — 79 series classified into tiers A (priced),
  B (priceable, uncovered — edge candidates), C (priceable, needs modeling), D (out of
  scope), X (not men's soccer WC). Machine-readable source of truth.
- NEW `docs/market_map.md` — human-readable version + the 18 tier-B edge candidates.
- `scripts/23_map_model_vs_market.py` repointed to read `kalshi_full_inventory.parquet`
  (superset of the old file; verified safe — needs only market_ticker/title/mid/volume).
- `scripts/morning.sh` runs 34 where 22 ran. `scripts/22_kalshi_discover.py` DEPRECATED
  (banner added; out of pipeline; deletable).
**Result:** complete board known; 18 tier-B surfaces identified as edge candidates (pending
F3). Maintenance contract: new *markets* auto-flow in; new *families* cost one CSV row.

## 2026-07-01 — [F5] Stop tracking daily data/report churn in git
**Status: DONE + committed (e5cbad2, 2ef5054).**
Git was drowning in regenerated parquets/reports, burying real code diffs. `.gitignore`
now excludes the daily DATA artifacts (`results`, `shootouts`, `goalscorers`,
`kalshi_wc_contracts.*`, `kalshi_full_inventory.*`, `model_vs_market`,
`tournament_probs_live`, scorecard, `derived_calibration.json`, raw results/goals) and the
regenerated REPORTS (`reports/daily/`, `cross_market_check.md`, `knockout_live_probs.md`,
`market_inventory.md`, `derived_calibration_*.md`). Frozen model inputs + curated files
(`wc_market_map.csv`, docs) STAY tracked — they are the reproducible state.

## 2026-07-01 — [F1] Single live-sim source for progression probabilities
**Status: DONE + committed (d974d8f).**
Three sources of "the model's progression probability" existed and consumers disagreed —
the advance pricer was silently reading the stale June sim while the live sim sat unused
(the exact class of bug that mispriced the advance sleeve). Fix: `scripts/23` now melts the
live bracket sim (`tournament_probs_live.parquet` from script 32) into `model_fv`, uses
`team_features` only for team-name matching, and no longer touches the stale
`fair_values_2026`. `morning.sh` reordered so 32 → 23 → 05. Dry-run confirmed
behavior-preserving (de-vig maxes at 0.925, no >100% probs). Permanently kills the
stale-source bug class for progression.

## 2026-06-29 — Advance-market pivot + collaboration principle + WebSocket plan
**Status: recorded in handoff §0/§2.0/§6; advance sleeve since revived (see F1).**
Regulation moneyline is the wrong knockout surface (draws in 90 go to ET, so "NO in reg"
pays on draws — artifact, not edge). Pivot to per-game advance markets. Added §2.0
collaboration principle (delegate sandbox-impossible steps to the Mac; don't downgrade to
inferior workarounds). Scoped a Mac-side WebSocket live-quote logger (still to build).

## 2026-07-01 — [F4] Collapse two WC schedules into one morning routine
**Status: DONE (scheduled-tasks updated).**
The settlement loop (09:09) and trade-ideas digest (09:34) both guarded on the same
`STATUS.json` and read the same Mac `morning.sh` output 25 min apart. Merged: the digest
task (`wc-trade-ideas-digest`, 09:34) now settles/syncs `trade_log.md` first, then produces
the digest — every step of both preserved, in sequence. The settlement task
(`wc-paper-trading-settlement-loop`) is **disabled** (paused, not deleted; re-enable to
un-merge). The unrelated 10:07 `daily-morning-briefing` is untouched.

## 2026-07-01 — [F6] Script index instead of physical relocation
**Status: DONE (scripts/README.md).**
Audit suggested moving one-off/debug scripts into `scripts/stage1/`. On inspection all
seven resolve the repo root via `parents[1]`, so relocating them one level deeper would
break path resolution and churn frozen files for a cosmetic gain. Instead added
`scripts/README.md` classifying every script as DAILY (the ~11-script live pipeline),
STAGE-1 (frozen, do-not-run), BACKTEST, DEBUG (verified unreferenced), or DEPRECATED.
Achieves F6's goal — make the live surface obvious — without breakage. (Physical move
remains available later if desired, with a `parents[1]→parents[2]` fix.)

---

## Backlog (decided-to-do, not yet done)
- **WebSocket live-pricer** — Mac-side socket → `live_quotes.parquet`; the real-time layer
  after discovery (handoff §6 item 0b).
- **Tier-B edge scan** — point the corrected-edge scan at a tier-B surface; blocked on F3.
