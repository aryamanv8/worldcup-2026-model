# WC-2026 Kalshi market map

Canonical reference for **every live Kalshi World Cup market family** and whether our
engine can price it. Machine-readable source of truth: `data/reference/wc_market_map.csv`
(one row per series). Produced/refreshed by `scripts/34_market_inventory.py`.

Last full inventory: **2026-07-01** — 77 live men's-soccer-WC series, ~4,290 markets.

## Why this exists
Two older discoverers each saw only a slice of the board (script 22 probed a *guessed*
series list; paper-trading 01 kept only already-priceable per-match types). Neither could
answer *"are we seeing all the markets?"*. Script 34 discovers the full catalog and tags
each series against this map, so coverage gaps are explicit and new families can't be
silently missed.

## Tiers
- **A — priced now.** Live sleeves. 4 series.
- **B — priceable, clean fit, NOT yet covered.** Our existing goal-grid or bracket-sim
  produces the fair value directly; only a reader/pricer is missing. **These are the edge
  candidates.** 18 series.
- **C — priceable with extra modeling.** Needs one added assumption (half-time goal split,
  draw-path combinatorics, 3rd-place logic, tournament-goal aggregation). 18 series.
- **D — out of scope.** Player props, corners, off-field novelty. A team-strength goals
  model has no view; correctly ignored. 36 series.
- **X — excluded.** Not the men's soccer WC (e.g. `KXWT20WORLDCUP` = women's cricket).

## The discipline caveat
**More surfaces ≠ more edge.** Our standing thesis (technical_record §12.4) is that the
market is efficient and our frozen-strength model mostly disagrees because the market has
newer info. This map does not hand us money — it tells us which surfaces our engine can
even generate a fair value for, so the corrected-edge scan can be pointed at them and we
can see whether anything survives de-vig + correction-toward-market. Same rules apply:
correct toward market, trade only calibrated/gated surfaces.

## Tier A — priced now
| series | engine | pricer |
|---|---|---|
| `KXWCGAME` | goal_grid | paper_trading/02 (VALIDATED) |
| `KXWCTOTAL` | goal_grid | paper_trading/04 (CALIBRATED, over_2.5 BLOCKED) |
| `KXWCBTTS` | goal_grid | paper_trading/04 (CALIBRATED, tiny) |
| `KXWCADVANCE` | bracket_sim | paper_trading/05 (GATED) |

## Tier B — edge candidates (priceable now, uncovered)
Ranked by liquidity. Bracket-sim ones reuse the exact machinery of the advance sleeve.

| series | engine | model output | ~volume |
|---|---|---|---:|
| `KXMENWORLDCUP` | bracket_sim | P(win tournament) — sim computes it, untraded | 562.8M |
| `KXWCROUND` | bracket_sim | P(reach round R) | 14.0M |
| `KXWCSTAGEOFELIM` | bracket_sim | P(eliminated at stage S) | 5.1M |
| `KXWCCONTINENT` | bracket_sim | P(confederation wins) | 3.5M |
| `KXWCFURTHESTADVANCING` | bracket_sim | P(furthest-advancing of confed) | 2.2M |
| `KXWCSCORE` | goal_grid | P(exact scoreline) — high vig, edge unlikely | 1.9M |
| `KXWCSPREAD` | goal_grid | P(margin ≥ handicap) — F7 | 1.2M |
| `KXWCGROUPWINNER` | bracket_sim | P(a group-G team wins) | 0.7M |
| `KXWCGROUPWINELIM` | bracket_sim | P(≥k group winners out by R32) | 0.6M |
| `KXWCBESTHOST` | bracket_sim | P(host X furthest of USA/CAN/MEX) | 0.4M |
| `KXWCTEAMH2H` | bracket_sim | P(two teams same elim stage) | 0.4M |
| `KXWCFIFATOP10` | bracket_sim | P(non-top-10 reaches semis) | 0.4M |
| `KXWCSTAGE` | bracket_sim | P(confed max stage = S) | 0.3M |
| `KXWCNOEURSA` | bracket_sim | P(winner outside UEFA/CONMEBOL) | 0.3M |
| `KXWC1STTIMEWIN` | bracket_sim | P(first-time winner) | 0.3M |
| `KXWCTEAMTOTAL` | goal_grid | P(team goals ≥ line) marginal Poisson | 0.3M |
| `KXWCMOV` | goal_grid | P(named team wins in reg) — overlaps moneyline | 0.2M |
| `KXWCMOF` | goal_grid | P(decided in reg) = 1 − P(draw) | 0.01M |

## Tier C — priceable, needs extra modeling
Half markets (`KXWC1H*`, `KXWC2H*`) need a half-time goal-split calibration.
Path markets (`KXWCMATCHUP`, `KXWCUSAOPPONENT`, `KXWCTEAMSINGAME`) need draw-path
combinatorics over the sim. Also `KXWC3RDPLACE` (3rd-place-match logic),
`KXWCKOPENALTIES` (per-match draw→shootout), `KXWCTOTALGOAL`/`KXWCTEAMTOTALGOALS`/
`KXWCGAMEGOALS` (tournament goal aggregation), `KXWCFTTS` (first-to-score race).

## Tier D / X — not ours
Player props (goals, assists, top scorer, awards, Messi/Ronaldo), corners, off-field
novelty (halftime show/song, Trump attendance, ticket price, 2038 host), and non-soccer
tournaments. No model surface — do not price.

## Housekeeping rules
- **New series appear as `UNKNOWN — review`** in the inventory report. When one shows up,
  read its title, add a row to `wc_market_map.csv`, re-run 34. Never let it stay UNKNOWN.
- **Zero-market series** (listed but not yet open) are intentionally not pre-classified;
  they're classified the first time they carry markets.
- `scripts/22_kalshi_discover.py` is **deprecated** (superseded by 34); safe to remove
  once you've confirmed 34 fully covers the daily path.
