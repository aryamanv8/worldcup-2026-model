# Trade Log — WC 2026 Paper Portfolio

> Running ledger for the paper-trading experiment. **No real money.** Update the
> portfolio summary as positions open and settle. Rules live in `README.md`.

---

## Portfolio summary

| Metric | Value |
|---|---|
| As of | 2026-06-13 |
| Starting bankroll | $500.00 |
| Cash | $416.59 |
| Open exposure (cost basis) | $98.60 |
| Realized P&L | +$15.19 |
| Unrealized P&L | $0.00 (cost-basis only, not marked-to-market) |
| **Total equity** | **$515.19** |
| Open positions | 3 |
| Settled trades | 1 |
| Win rate (settled) | 100% (1/1) — see note below |

> **Note on win rate:** the one settled trade (Brazil vs Morocco, tag `reliable`)
> is a near-even matchup, not part of the `favorite-fade` thesis. The three open
> `favorite-fade` positions are the actual experiment (technical record §12);
> 1/1 here says nothing about that question yet.

---

## Open positions

| # | Opened | Market | Ticker | Side | Entry ¢ | Qty | Stake $ | Fee $ | Cost $ | Model FV % | Net edge ¢ | Notes |
|---|--------|--------|--------|------|---------|-----|---------|-------|--------|------------|------------|-------|
| 1 | 2026-06-13 | Turkiye vs Paraguay | KXWCGAME-26JUN19TURPAR-PAR | BUY YES | 24 | 125 | 30.00 | 1.60 | 31.60 | 42.3 | +17.0 | Paraguay; Elo +48, reliable; favorite-fade |
| 2 | 2026-06-13 | Ecuador vs Germany | KXWCGAME-26JUN25ECUGER-GER | BUY NO | 45 | 82 | 36.90 | 1.43 | 38.33 | 61.4 | +14.7 | Germany not to win in reg; Elo +26, reliable; favorite-fade |
| 3 | 2026-06-13 | Austria vs Jordan | KXWCGAME-26JUN17AUTJOR-AUT | BUY NO | 27 | 101 | 27.27 | 1.40 | 28.67 | 43.0 | +14.6 | Austria not to win in reg; Elo +110, reliable; favorite-fade |

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

**Austria vs Jordan** · Wed Jun 17, 2026 · group stage
- Bet: **BUY NO @ Austria** (Austria does not win in regulation)
- Market: KXWCGAME-26JUN17AUTJOR-AUT
- Entry 0.27 · Qty 101 · Stake $27.27 + fee $1.40 = **cost $28.67**
- Model FV (NO) 0.430 · net edge +14.6¢/ct · Elo +110, reliable · tag: favorite-fade
- Payoff if win: **+$72.33**; if lose: **−$28.67** · Closing price: _(fill at kickoff)_ · Result: _(TBD)_ · Status: **OPEN**

---

## Settled trades

| # | Opened | Settled | Match | Side | Entry ¢ | Qty | Cost $ | Outcome | Payoff $ | Realized P&L $ | Bankroll $ |
|---|--------|---------|--------|------|---------|-----|--------|---------|----------|----------------|------------|
| 1 | 2026-06-12 | 2026-06-13 | Brazil vs Morocco | BUY NO @ Brazil | 42 | 27 | 11.81 | TIE 1-1 (reg.) | 27.00 | +15.19 | 515.19 |

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