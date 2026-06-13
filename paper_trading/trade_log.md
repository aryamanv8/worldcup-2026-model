# Trade Log — WC 2026 Paper Portfolio

> Running ledger for the paper-trading experiment. **No real money.** Update the
> portfolio summary as positions open and settle. Rules live in `README.md`.

---

## Portfolio summary

| Metric | Value |
|---|---|
| As of | 2026-06-12 |
| Starting bankroll | $500.00 |
| Cash | $488.19 |
| Open exposure (cost basis) | $11.81 |
| Realized P&L | $0.00 |
| Unrealized P&L | $0.00 |
| **Total equity** | **$500.00** |
| Open positions | 1 |
| Settled trades | 0 |
| Win rate (settled) | — |

---

## Open positions

| # | Opened | Market | Ticker | Side | Entry ¢ | Qty | Stake $ | Fee $ | Cost $ | Model FV % | Net edge ¢ | Notes |
|---|--------|--------|--------|------|---------|-----|---------|-------|--------|------------|------------|-------|

| 1 | 2026-06-12 | Brazil vs Morocco | KXWCGAME-26JUN13BRAMAR-BRA | BUY NO | 42 | 27 | 11.34 | 0.47 | 11.81 | 47.4 | +3.7 | Brazil not to win in reg; Elo +78, reliable |

### OPEN — 2026-06-12

**Brazil vs Morocco** · Sat Jun 13, 2026 · group stage
- Bet: **BUY NO @ Brazil** (Brazil does not win in regulation)
- Market: KXWCGAME-26JUN13BRAMAR-BRA
- Entry ask: 0.42 · Contracts: 27 · Stake: $11.34 + fee $0.47 = **cost $11.81**
- Model fair value (NO): 0.474 · net edge +3.7¢/ct
- Reliable zone: Elo gap +78 (50–150 bucket, |Δexp|=0.006)
- Payoff if win: $27 → **P&L +$15.19**; if lose: **−$11.81**
- Closing price: _(fill at kickoff)_ · Result: _(fill after match)_ · Status: **OPEN**

---

## Settled trades

| # | Opened | Settled | Market | Side | Entry ¢ | Qty | Cost $ | Outcome | Payoff $ | Realized P&L $ | Bankroll $ |
|---|--------|---------|--------|------|---------|-----|--------|---------|----------|----------------|------------|
| _none yet_ | | | | | | | | | | | |

---

## P&L history

| Date | Event | Realized P&L $ | Total equity $ | Note |
|------|-------|----------------|----------------|------|
| — | Portfolio opened | 0.00 | 500.00 | $500 paper bankroll |

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