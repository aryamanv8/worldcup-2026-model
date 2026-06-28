# Derived-market calibration gate — 2026-06-28 00:53Z

OOS matches: **256** · Dixon-Coles rho: -0.0246 · source: `data/processed/backtest_predictions.csv`

## Verdict

| market | n | base | log loss | baseline | beats? | bin MAE | PASS |
|---|---|---|---|---|---|---|---|
| over_0.5 | 256 | 0.91 | 0.2960 | 0.2930 | NO | 0.014 | FAIL |
| over_1.5 | 256 | 0.70 | 0.6080 | 0.6082 | yes | 0.028 | PASS |
| over_2.5 | 256 | 0.49 | 0.6997 | 0.6929 | NO | 0.110 | FAIL |
| over_3.5 | 256 | 0.23 | 0.5394 | 0.5351 | NO | 0.074 | FAIL |
| over_4.5 | 256 | 0.13 | 0.3841 | 0.3843 | yes | 0.275 | FAIL |
| btts | 256 | 0.49 | 0.6923 | 0.6929 | yes | 0.004 | PASS |

**Tradeable now (per-market gate): over_1.5, btts**
**Blocked (do NOT trade): over_0.5, over_2.5, over_3.5, over_4.5**

> The pricer keys off the per-market `pass` flags in `derived_calibration.json`, not the all-or-nothing summary. A market trades only if it passed here.

## Reliability (predicted vs realized)

### over_0.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.8,0.9] | 24 | 0.894 | 0.917 |
| (0.9,1.0] | 232 | 0.918 | 0.914 |

### over_1.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.6,0.7] | 70 | 0.683 | 0.686 |
| (0.7,0.8] | 182 | 0.731 | 0.709 |
| (0.8,0.9] | 4 | 0.810 | 0.750 |

### over_2.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.3,0.4] | 14 | 0.390 | 0.643 |
| (0.4,0.5] | 190 | 0.449 | 0.479 |
| (0.5,0.6] | 52 | 0.527 | 0.481 |

### over_3.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.1,0.2] | 17 | 0.192 | 0.294 |
| (0.2,0.3] | 212 | 0.244 | 0.222 |
| (0.3,0.4] | 27 | 0.320 | 0.222 |

### over_4.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.0,0.1] | 74 | 0.090 | 0.108 |
| (0.1,0.2] | 181 | 0.122 | 0.133 |
| (0.2,0.3] | 1 | 0.203 | 1.000 |

### btts  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.4,0.5] | 194 | 0.473 | 0.479 |
| (0.5,0.6] | 62 | 0.516 | 0.516 |
