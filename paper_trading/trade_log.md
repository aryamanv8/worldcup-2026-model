# Trade Log — WC 2026 Paper Portfolio

> Running ledger for the paper-trading experiment. **No real money.** Update the
> portfolio summary as positions open and settle. Rules live in `README.md`.

---

## Portfolio summary

| Metric | Value |
|---|---|
| As of | _not started_ |
| Starting bankroll | $500.00 |
| Cash | $500.00 |
| Open exposure (cost basis) | $0.00 |
| Realized P&L | $0.00 |
| Unrealized P&L | $0.00 |
| **Total equity** | **$500.00** |
| Open positions | 0 |
| Settled trades | 0 |
| Win rate (settled) | — |

---

## Open positions

| # | Opened | Market | Ticker | Side | Entry ¢ | Qty | Stake $ | Fee $ | Cost $ | Model FV % | Net edge ¢ | Notes |
|---|--------|--------|--------|------|---------|-----|---------|-------|--------|------------|------------|-------|
| _none yet_ | | | | | | | | | | | | |

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
- **Model FV %** — model's fair value for the YES outcome.
- **Net edge ¢** — `(Model FV − Entry) × 100 − fee/contract`, the per-contract edge after fees.
- **Payoff $** — `Qty × $1` if the position wins, else `$0`.
- **Realized P&L $** — `Payoff − Cost` (single-leg; subtract exit fee if closed early).
- **Bankroll $** — running paper bankroll after the trade settles.