# Paper Trading — Live World Cup 2026 Experiment

A capital-free, live paper-trading experiment that operationalizes the Stage 1
model and the Stage 2 market findings. **No real money is involved.** The goal is
to (a) settle empirically whether the model's divergence from the market is real
edge or model bias, by letting the tournament adjudicate, and (b) learn the full
quant trading loop — sizing, execution, settlement, P&L attribution.

This stage is kept self-contained in `paper_trading/`. It does not alter the
Stage 1 model or pipeline.

---

## Why this exists

Stage 2 established that the liquid **outright** markets (champion, reach-round) are
efficient: no intra-Kalshi arbitrage, dutch books negative after fees, and the
model-vs-market gaps are favorite-longshot bias plus the model's mid-tier lean —
not a bankable edge with real money. With money off the table, those same
divergences become a clean, no-downside **experiment**: trade the model's signal on
paper across a whole World Cup and see whether it makes paper P&L. The tournament
is the judge.

The model's strongest, most-validated ground is **individual matches** (OOS log
loss 0.967; calibrated; rated every historical champion top-3). Per-match markets
also resolve in hours, giving fast feedback. So match markets are the primary venue;
a diversified slice of reach-round value picks tests the headline divergence.

---

## Portfolio rules

| Rule | Value |
|---|---|
| Starting bankroll | **$500** (paper) |
| Position sizing | **Quarter-Kelly**: `size = 0.25 × f* × bankroll`, where `f* = (p − a) / (1 − a)` |
| | `p` = model fair value, `a` = entry ask (both in 0..1) |
| Per-position cap | **10% of current bankroll** |
| Minimum position | skip if stake < **$5** (fees dominate tiny trades) |
| Entry filter | model in a **reliable zone** AND **net edge ≥ 3¢/contract after fees** AND real liquidity |
| Fees | Kalshi taker: `ceil_cents(0.07 × C × P × (1−P))`; resting limit orders treated as free (maker) |
| Settlement | at real outcome; payoff = $1/contract if YES resolves true, else $0 |

### Why quarter-Kelly

Full Kelly `f* = (p − a)/(1 − a)` maximizes long-run log-growth **if** the model
probability `p` is exactly right. It isn't — `p` is an estimate — so full Kelly
over-bets and is brutally volatile. Quarter-Kelly keeps most of the growth with a
fraction of the variance, and the 10% cap is a hard backstop against the model's
most aggressive (and least trustworthy) divergence picks.

**Worked example.** Model `p = 0.435` (a team to reach R16), ask `a = 0.21`.
`f* = (0.435 − 0.21)/(1 − 0.21) = 0.285`. Quarter-Kelly = `0.071 × $500 = $35.60`
(under the $50 cap). Contracts = `35.60 / 0.21 ≈ 169`. Fee =
`ceil(0.07 × 169 × 0.21 × 0.79) = $1.97`. Total cost ≈ **$37.46**. If it resolves
YES: payoff $169, P&L ≈ **+$131.54**; if NO: P&L ≈ **−$37.46**.

---

## The loop

1. **Discover** — pull the live/upcoming Kalshi WC markets (match markets first).
2. **Price** — model fair value per market + its model-card reliability zone.
3. **Filter** — keep only reliable-zone markets clearing the net-edge threshold.
4. **Log** — record the trade with full detail in `trade_log.md` (and your notepad).
5. **Settle** — when the event resolves, book payoff, realized P&L, new bankroll.
6. **Review** — every few days, attribute P&L by strategy/market and adjust which
   signals we trust. This review *is* the strategy development.

---

## Folder layout

```
paper_trading/
  README.md        # this file — methodology + rules
  trade_log.md     # the running ledger: portfolio summary, open + settled trades
  scripts/         # stage scripts: market discovery, pricing/signals, settlement
  data/            # live market snapshots pulled for paper trading
```

Stage-specific scripts live here (not in the top-level numbered `scripts/`) to keep
the trading stage cohesive and separable from the model pipeline.

---

## Honest expectation

If the match markets are as efficient as the outrights, paper P&L grinds around
break-even-after-fees and the lesson is "even a calibrated model can't beat an
efficient market after costs." If there's a soft pocket in the lower-attention
group-stage match markets, the loop should surface it. Either result is a genuine,
documentable outcome — and watching the model's value picks resolve across a whole
tournament is the best learning available here.