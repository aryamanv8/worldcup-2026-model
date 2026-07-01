# Architecture audit — worldcup-2026-model (2026-07-01)

Working audit produced to answer: *are our scripts/routines/schedules actually
talking to each other, and does the engine price what Kalshi is actually selling?*
This document is a **map + findings + consolidation plan**. It is meant to be acted
on and then folded into `handoff.md`/`technical_record.md` — not kept forever.

---

## 1. What actually runs, and in what order

**Model library (one source of truth — good).** `src/wc2026/`: `models/poisson.py`
(`predict_match_dc`) + `simulation/engine.py` (`recalibrate_score_matrix`). Everything
that needs a match prediction loads the same three frozen artifacts:
`models/poisson_v1.pkl`, `team_features.parquet`, `calibration.json` (T=0.77).

**Three layers of scripts:**

| Layer | Scripts | Cadence | Notes |
|---|---|---|---|
| Stage-1 build (frozen) | `01`–`21`, `25` | one-time, DO NOT RE-RUN | builds results/elo/features/model/backtests/`fair_values_2026`. Already on the "don't run" list. |
| Daily pipeline (`morning.sh`, launchd 07:30 Mac) | `01_fetch_results`, pt`03_settle`, `28_score`, pt`01_discover`, pt`02_price`, `30_calibrate`, pt`04_derived`, `22_discover`, `23_map`, `32_live_sim`, pt`05_advance`, `24_arb`, `33_xmarket` | daily | writes `reports/daily/<date>/` |
| Analysis-only | `24`, `32`, `33` | daily | arb scan, live bracket sim, cross-market check |

**Claude schedules (read the Mac output, add reasoning):**

| Task | Time | Reads |
|---|---|---|
| `wc-paper-trading-settlement-loop` | 09:09 | Mac pipeline output; syncs trade_log |
| `wc-trade-ideas-digest` | 09:34 | same daily slate; reasons over candidates |
| `daily-morning-briefing` | 10:07 | unrelated (email/calendar) |

---

## 2. Market ↔ model mapping — VERIFIED CORRECT

The engine does distinguish Kalshi's market types, using the same frozen model for all:

| Kalshi market | Series | Priced by | Model output | Correct? |
|---|---|---|---|---|
| Regulation moneyline | `KXWCGAME` | pt`02` | grid → P(win in 90) / P(draw) / P(lose) | ✅ |
| To-advance / reach round | `KXMENWORLDCUP`, `KXWCROUND-*` | `32`→pt`05` | P(win reg) + P(draw)·0.5 shootout, exact bracket DP | ✅ correctly ≠ regulation |
| Totals (O/U) | `KXWCTOTAL` | pt`04` | grid total-goals | ✅ (only over_1.5/btts calibrated) |
| BTTS | `KXWCBTTS` | pt`04` | grid BTTS | ✅ live tiny experiment |
| Spread / handicap | `KXWCSPREAD` | — | helper exists | ⚠️ discovered, never priced |

**One real limitation (not a bug):** the bracket is live (`32`), but **team strength is
frozen pre-tournament** (`team_features.parquet` + frozen model, by design). So reach
probabilities know *who* is left but rate them at *June* strength, not group-stage form.
This is why the model likes teams the market has downgraded (Bosnia 58% reach-R16 vs
market 18%) and why the corrected advance slate is near-empty. **Decision needed:** keep
frozen strength, or build a *controlled* knockout form-refresh.

---

## 3. Findings — where things don't talk to each other

**F1 — Three progression-model sources; consumers disagree (root cause of today's bug).**
`21`→`fair_values_2026.parquet` (frozen Jun-11) → merged by `23` as `model_fv` in
`model_vs_market.parquet`; but `32`→`tournament_probs_live.parquet` is the live truth.
pt`05` was reading the stale one (fixed today by overriding), `33` reads live directly,
`24` reads the stale MVM. **Fix:** make `23` merge the LIVE sim as `model_fv` so every
downstream consumer (`05`/`24`/`33`) sees one coherent model; retire `21` +
`fair_values_2026` + `simulation_results` from the daily path (keep as Stage-1 artifacts).

**F2 — Two independent Kalshi discovery scripts; full coverage NOT guaranteed.**
pt`01` discovers match markets (`KXWCGAME/SPREAD/TOTAL/BTTS`); `22` discovers outrights
using **guessed** series tickers (`KXMENWORLDCUPADVANCE  # (guess)`). Neither enumerates
the live catalog exhaustively. This is exactly "are we seeing all markets?" **Fix:** one
unified discovery that lists ALL `KXWC*`/`KXMEN*` series from Kalshi's catalog into a
single market inventory both pricers read. (This is also step 1 of the WebSocket plan.)

**F3 — Frozen strength vs live bracket** — see §2 limitation. A product decision, not a
wiring fix.

**F4 — Two Claude schedules read the same daily output** (09:09 settlement, 09:34 digest).
Collapse into one "WC morning routine" that settles → syncs → reasons in sequence.

**F5 — Git history is drowning in data churn.** 22 uncommitted paths right now, most of
them regenerated parquets (`results`, `kalshi_wc_contracts`, `model_vs_market`,
`scorecard`) + accumulating `reports/derived_calibration_*.md` (one per run, untracked).
Real code diffs get lost. **Fix:** stop committing daily-regenerated data + reports
(`.gitignore` them, or snapshot on a separate cadence); keep git for code + docs +
decisions. Add report retention (keep last N days).

**F6 — One-time/debug scripts sit next to daily scripts.** `07`,`11`,`12`–`16` (sanity,
diagnostics, transfermarkt exploration, dtype audits) are Stage-1/debug scaffolding.
**Fix:** move to `scripts/stage1/` (or `archive/`) with a one-line README so the daily
surface is small and obvious.

**F7 — Spread (`KXWCSPREAD`) is discovered but never priced.** Minor; either wire it
(after totals validate) or stop discovering it.

---

## 4. Keep / archive / merge

| Action | Items |
|---|---|
| **Keep (daily, live)** | `src/wc2026`, `01_fetch`, pt`01`–pt`05`, `22`, `23`(→fix F1), `28`, `30`, `32`, `24`, `33`, `26_fee`, `morning.sh` |
| **Keep (frozen Stage-1)** | `02`–`21`, `25` — move to `scripts/stage1/` (F6) |
| **Retire from daily path** | `21`+`fair_values_2026`+`simulation_results` as a *model source* (F1) |
| **Merge** | the two Claude schedules → one morning routine (F4); the two discovery scripts → one inventory (F2) |
| **Decide** | frozen strength vs knockout form-refresh (F3) |
| **Hygiene** | gitignore daily data/reports + retention (F5); wire or drop spread (F7) |

## 5. Needs a Mac run (delegated to Aryaman)
- Unified market discovery against the live Kalshi catalog (F2) — the real inventory.
- Any re-run of `morning.sh` to confirm the F1 rewire once `23` is changed.
- `git` commit/`.gitignore` changes (I can't push from the sandbox).
