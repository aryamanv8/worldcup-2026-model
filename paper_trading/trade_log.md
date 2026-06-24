# Trade Log — WC 2026 Paper Portfolio

> Running ledger for the paper-trading experiment. **No real money.** Update the
> portfolio summary as positions open and settle. Rules live in `README.md`.

---

## Portfolio summary

| Metric | Value |
|---|---|
| As of | 2026-06-24 |
| Starting bankroll | $500.00 |
| Cash | $570.25 |
| Open exposure (cost basis) | $38.33 |
| Realized P&L | +$108.58 |
| Unrealized P&L | $0.00 (cost-basis only, not marked-to-market) |
| **Total equity** | **$608.58** |
| Open positions | 1 |
| Settled trades | 5 |
| Win rate (settled) | 80% (4/5) — see note below |

> **Note on win rate:** four settled trades — Brazil vs Morocco (tag `reliable`,
> a near-even matchup) won; Turkiye vs Paraguay (tag `favorite-fade`) won;
> Austria vs Jordan (tag `favorite-fade`) lost; Mexico vs Korea (tag
> `favorite-boost`) closed early for a gain. The favorite-fade thesis is now
> **1/2 live** (Paraguay won, Austria lost), with one fade still open (Germany) —
> that basket is what bears on the experiment. The Mexico result is a profitable
> **early cash-out** (sold before settlement, not held to the regulation result),
> so it speaks to exit timing rather than the favorite-boost edge holding to
> settlement. Norway vs Senegal (tag `favorite-boost`) won held-to-settlement
> (Norway 3–2), the first favorite-boost result actually carried to the whistle.

---

## Open positions

| # | Opened | Market | Ticker | Side | Entry ¢ | Qty | Stake $ | Fee $ | Cost $ | Model FV % | Net edge ¢ | Notes |
|---|--------|--------|--------|------|---------|-----|---------|-------|--------|------------|------------|-------|
| 2 | 2026-06-13 | Ecuador vs Germany | KXWCGAME-26JUN25ECUGER-GER | BUY NO | 45 | 82 | 36.90 | 1.43 | 38.33 | 61.4 | +14.7 | Germany not to win in reg; Elo +26, reliable; favorite-fade |

### OPEN — 2026-06-13

**Ecuador vs Germany** · Thu Jun 25, 2026 · group stage
- Bet: **BUY NO @ Germany** (Germany does not win in regulation)
- Market: KXWCGAME-26JUN25ECUGER-GER
- Entry 0.45 · Qty 82 · Stake $36.90 + fee $1.43 = **cost $38.33**
- Model FV (NO) 0.614 · net edge +14.7¢/ct · Elo +26, reliable · tag: favorite-fade
- Payoff if win: **+$43.67**; if lose: **−$38.33** · Closing price: _(fill at kickoff)_ · Result: _(TBD)_ · Status: **OPEN**

---

## Settled trades

| # | Opened | Settled | Match | Side | Entry ¢ | Qty | Cost $ | Outcome | Payoff $ | Realized P&L $ | Bankroll $ |
|---|--------|---------|--------|------|---------|-----|--------|---------|----------|----------------|------------|
| 1 | 2026-06-12 | 2026-06-13 | Brazil vs Morocco | BUY NO @ Brazil | 42 | 27 | 11.81 | TIE 1-1 (reg.) | 27.00 | +15.19 | 515.19 |
| 2 | 2026-06-13 | 2026-06-21 | Turkiye vs Paraguay | BUY YES @ Paraguay | 24 | 125 | 31.60 | PAR win 1-0 (reg.) | 125.00 | +93.40 | 591.22 |
| 4 | 2026-06-13 | 2026-06-18 | Austria vs Jordan | BUY NO @ Austria | 27 | 101 | 28.67 | AUT win 3-1 (reg.) | 0.00 | −28.67 | 486.52 |
| 5 | 2026-06-18 | 2026-06-18 | Mexico vs Korea Republic | BUY YES @ Mexico | 48 | 31 | 15.43 | Early cash-out @ ~86¢ | 26.73 | +11.30 | 497.82 |
| 6 | 2026-06-21 | 2026-06-24 | Norway vs Senegal | BUY YES @ Norway | 44 | 32 | 14.64 | NOR win 3-2 (reg.) | 32.00 | +17.36 | 608.58 |

### SETTLED — 2026-06-24

**Norway vs Senegal** · Mon Jun 22, 2026 · group stage
- Bet: **BUY YES @ Norway** (Norway wins in regulation) · tag: favorite-boost
- Market: KXWCGAME-26JUN22NORSEN-NOR
- Entry 0.44 · Qty 32 · Stake $14.08 + fee $0.56 = **cost $14.64**
- Model fair value (Norway): 0.505 · net edge +4.7¢/ct · tag: favorite-boost
- Result: **Norway 3–2 Senegal (reg.)** (source `data/raw/results.csv`) → YES @ Norway settles **WIN**
- Payoff: $32.00 · **Realized P&L: +$17.36** · Bankroll: $591.22 → **$608.58** · Status: **SETTLED — WIN**
- Note: first favorite-boost position held to settlement (the Mexico boost was an early cash-out), so this is the first clean held-to-whistle favorite-boost data point.

### SETTLED — 2026-06-21

**Turkiye vs Paraguay** · Fri Jun 19, 2026 · group stage
- Bet: **BUY YES @ Paraguay** (model made Paraguay the favorite over Turkiye) · tag: favorite-fade
- Market: KXWCGAME-26JUN19TURPAR-PAR
- Entry 0.24 · Qty 125 · Stake $30.00 + fee $1.60 = **cost $31.60**
- Model fair value (Paraguay): 0.423 · net edge +17.0¢/ct · Elo +48, reliable · tag: favorite-fade
- Result: **Turkey 0–1 Paraguay (reg.)** (Santa Clara; source `data/raw/results.csv`) → YES @ Paraguay settles **WIN**
- Payoff: $125.00 · **Realized P&L: +$93.40** · Status: **SETTLED — WIN**

### SETTLED — 2026-06-18 (cash-out)

**Mexico vs Korea Republic** · Thu Jun 18, 2026 · group stage
- Bet: **BUY YES @ Mexico** (Mexico to win in regulation) · tag: favorite-boost
- Market: KXWCGAME-26JUN18MEXKOR-MEX
- Entry 0.48 · Qty 31 · cost **$15.43** (user-quoted $15.42; 1¢ fee rounding — booked basis kept at $15.43)
- Exit: **closed early before settlement** for proceeds **$26.73** (≈86¢/ct net of exit fee)
- **Realized P&L: +$11.30** (26.73 − 15.43) · Bankroll: $486.52 → **$497.82** · Status: **SETTLED — CASH-OUT (gain)**
- Note: profitable exit taken before the regulation result; does not test whether the favorite-boost edge holds to settlement.

### SETTLED — 2026-06-18

**Austria vs Jordan** · Wed Jun 17, 2026 · group stage
- Bet: **BUY NO @ Austria** (Austria does not win in regulation)
- Market: KXWCGAME-26JUN17AUTJOR-AUT
- Entry ask: 0.27 · Contracts: 101 · Stake: $27.27 + fee $1.40 = **cost $28.67**
- Model fair value (NO): 0.430 · net edge +14.6¢/ct · Elo +110, reliable · tag: favorite-fade
- Result: **Austria won 3-1 (reg.)** → NO @ Austria settles **LOST**
- Payoff: $0.00 · **Realized P&L: −$28.67** · Status: **SETTLED — LOSS**

### SETTLED — 2026-06-13

**Brazil vs Morocco** · Sat Jun 13, 2026 · group stage
- Bet: **BUY NO @ Brazil** (Brazil does not win in regulation)
- Market: KXWCGAME-26JUN13BRAMAR-BRA
- Entry ask: 0.42 · Contracts: 27 · Stake: $11.34 + fee $0.47 = **cost $11.81**
- Model fair value (NO): 0.474 · net edge +3.7¢/ct
- Reliable zone: Elo gap +78 (50–150 bucket, |Δexp|=0.006) · tag: reliable
- Result: **1-1 draw** (Saibari 21', Vinicius Jr 32'; MetLife Stadium; confirmed
  via FIFA/ESPN) → NO @ Brazil settles **WIN**
- Payoff: $27.00 · **Realized P&L: +$15.19** · Status: **SETTLED — WIN**

---

## P&L history

| Date | Event | Realized P&L $ | Total equity $ | Note |
|------|-------|----------------|----------------|------|
| 2026-06-12 | Portfolio opened | 0.00 | 500.00 | $500 paper bankroll |
| 2026-06-13 | Brazil vs Morocco settled (NO @ Brazil, TIE 1-1) | +15.19 | 515.19 | tag: reliable; near-even matchup, not favorite-fade |
| 2026-06-18 | Austria vs Jordan settled (NO @ Austria, AUT win 3-1) | −28.67 | 486.52 | tag: favorite-fade; first live fade result — a loss |
| 2026-06-18 | Mexico vs Korea cashed out early (YES @ Mexico, proceeds $26.73) | +11.30 | 497.82 | tag: favorite-boost; early exit for a gain, not held to settlement |
| 2026-06-21 | Turkiye vs Paraguay settled (YES @ Paraguay, PAR win 1-0) | +93.40 | 591.22 | tag: favorite-fade; first favorite-fade win held to settlement |
| 2026-06-24 | Norway vs Senegal settled (YES @ Norway, NOR win 3-2) | +17.36 | 608.58 | tag: favorite-boost; first favorite-boost win held to settlement |

---

## Column definitions

- **Side** — `BUY YES` or `BUY NO` (NO = betting the event does not happen).
- **Entry ¢** — fill price in cents (= implied probability).
- **Qty** — number of contracts.
- **Stake $** — `Qty × Entry` (in dollars).
- **Fee $** — Kalshi taker fee, `ceil_cents(0.07 × Qty × P × (1−P))`.
- **Cost $** — `Stake + Fee` (total cash out).
- **Model FV %** — model's fair value for the **side bet** (for BUY NO, the complement: P(event does not happen)).
- **Net edge ¢** — `(Model FV − Entry) × 100 − fee/contract`, the per-contract edge after fees.
- **Payoff $** — `Qty × $1` if the position wins, else `$0`.
- **Realized P&L $** — `Payoff − Cost` (single-leg; subtract exit fee if closed early).
- **Bankroll $** — running paper bankroll after the trade settles.