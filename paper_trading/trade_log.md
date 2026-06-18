# Trade Log — WC 2026 Paper Portfolio

> Running ledger for the paper-trading experiment. **No real money.** Update the
> portfolio summary as positions open and settle. Rules live in `README.md`.

---

## Portfolio summary

| Metric | Value |
|---|---|
| As of | 2026-06-18 |
| Starting bankroll | $500.00 |
| Cash | $401.16 |
| Open exposure (cost basis) | $85.36 |
| Realized P&L | −$13.48 |
| Unrealized P&L | $0.00 (cost-basis only, not marked-to-market) |
| **Total equity** | **$486.52** |
| Open positions | 3 |
| Settled trades | 2 |
| Win rate (settled) | 50% (1/2) — see note below |

> **Note on win rate:** the two settled trades split — Brazil vs Morocco (tag
> `reliable`, a near-even matchup) won; Austria vs Jordan (tag `favorite-fade`)
> lost. The favorite-fade thesis is now 0/1 live (Austria), with two more fades
> open (Paraguay, Germany). This is the first live evidence on the question the
> experiment actually cares about (technical record §12), and it's consistent
> with the backtest's caution against favorite-fade.

---

## Open positions

| # | Opened | Market | Ticker | Side | Entry ¢ | Qty | Stake $ | Fee $ | Cost $ | Model FV % | Net edge ¢ | Notes |
|---|--------|--------|--------|------|---------|-----|---------|-------|--------|------------|------------|-------|
| 1 | 2026-06-13 | Turkiye vs Paraguay | KXWCGAME-26JUN19TURPAR-PAR | BUY YES | 24 | 125 | 30.00 | 1.60 | 31.60 | 42.3 | +17.0 | Paraguay; Elo +48, reliable; favorite-fade |
| 2 | 2026-06-13 | Ecuador vs Germany | KXWCGAME-26JUN25ECUGER-GER | BUY NO | 45 | 82 | 36.90 | 1.43 | 38.33 | 61.4 | +14.7 | Germany not to win in reg; Elo +26, reliable; favorite-fade |
| 3 | 2026-06-18 | Mexico vs Korea Republic | KXWCGAME-26JUN18MEXKOR-MEX | BUY YES | 48 | 31 | 14.88 | 0.55 | 15.43 | 54.3 | +4.5 | Mexico to win in reg; favorite-boost; thin edge — Montes susp., Quiñones doubt |

### OPEN — 2026-06-18

**Mexico vs Korea Republic** · Thu Jun 18, 2026 · group stage
- Bet: **BUY YES @ Mexico** (Mexico to win in regulation)
- Market: KXWCGAME-26JUN18MEXKOR-MEX
- Entry 0.48 · Qty 31 · Stake $14.88 + fee $0.55 = **cost $15.43**
- Model FV (Mexico reg. win) 0.543 · net edge +4.5¢/ct · tag: favorite-boost
- Lineup caveats at entry: César Montes suspended (starting CB), Julián Quiñones doubtful; edge is thin-to-breakeven after §12.4 haircut. Entered at full slate size (31 ct) by user decision.
- Payoff if win: **+$15.57**; if lose: **−$15.43** · Settles regulation result · Closing price: _(fill at kickoff)_ · Result: _(TBD)_ · Status: **OPEN**

### OPEN — 2026-06-13

**Turkiye vs Paraguay** · Fri Jun 19, 2026 · group stage
- Bet: **BUY YES @ Paraguay** (model makes Paraguay the favorite over Turkiye)
- Market: KXWCGAME-26JUN19TURPAR-PAR
- Entry 0.24 · Qty 125 · Stake $30.00 + fee $1.60 = **cost $31.60**
- Model FV (Paraguay) 0.423 · net edge +17.0¢/ct · Elo +48, reliable · tag: favorite-fade
- Payoff if win: **+$93.40**; if lose: **−$31.60** · Closing price: _(fill at kickoff)_ · Result: _(TBD)_ · Status: **OPEN**

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
| 4 | 2026-06-13 | 2026-06-18 | Austria vs Jordan | BUY NO @ Austria | 27 | 101 | 28.67 | AUT win 3-1 (reg.) | 0.00 | −28.67 | 486.52 |

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