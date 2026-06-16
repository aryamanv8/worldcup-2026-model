# Strategy backtest 20260616T031232Z

```
========================================================================
  HISTORICAL TRADING-STRATEGY BACKTEST
========================================================================
  group-stage matches evaluated : 96
  matches in reliable zone      : 50
  qualifying trades taken       : 42
  win rate                      : 18/42 = 42.9%
  total staked (cost basis)     : $1265.77
  total P&L                     : $+330.23
  ROI on staked                 : +26.1%
  mean net edge claimed         : +14.0c
  per-trade Sharpe-equivalent   : +0.16

  --- by signal tag ---
  favorite-boost   n= 23  win=48%  P&L=$ +363.82  ROI=+48.9%
  favorite-fade    n= 18  win=33%  P&L=$  -42.10  ROI=-8.4%
  neutral          n=  1  win=100%  P&L=$   +8.51  ROI=+41.5%

  --- by tournament ---
  2018     n= 21  win=48%  P&L=$ +204.78
  2022     n= 21  win=38%  P&L=$ +125.45

  --- calibration of taken bets (model_p vs realized win) ---
  model_p (0.0, 0.4]     n= 13  mean_p=0.323  realized=0.231
  model_p (0.4, 0.5]     n=  7  mean_p=0.452  realized=0.286
  model_p (0.5, 0.6]     n= 10  mean_p=0.542  realized=0.500
  model_p (0.6, 0.7]     n=  4  mean_p=0.677  realized=0.750
  model_p (0.7, 1.01]    n=  8  mean_p=0.735  realized=0.625
```
