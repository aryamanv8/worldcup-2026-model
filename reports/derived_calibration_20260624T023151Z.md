# Derived-market calibration gate — 2026-06-24 02:31Z

OOS matches: **256** · Dixon-Coles rho: 0.0000 · source: `data/processed/backtest_predictions.csv`

## Verdict

| market | n | base | log loss | baseline | beats? | bin MAE | PASS |
|---|---|---|---|---|---|---|---|
| over_0.5 | 256 | 0.91 | 0.2962 | 0.2930 | NO | 0.029 | FAIL |
| over_1.5 | 256 | 0.70 | 0.6078 | 0.6082 | yes | 0.055 | PASS |
| over_2.5 | 256 | 0.49 | 0.6997 | 0.6929 | NO | 0.110 | FAIL |
| over_3.5 | 256 | 0.23 | 0.5394 | 0.5351 | NO | 0.074 | FAIL |
| over_4.5 | 256 | 0.13 | 0.3841 | 0.3843 | yes | 0.275 | FAIL |
| btts | 256 | 0.49 | 0.6925 | 0.6929 | yes | 0.016 | PASS |

**Sleeve gate: FAIL — do NOT trade derived markets**

## Reliability (predicted vs realized)

### over_0.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.8,0.9] | 18 | 0.896 | 0.944 |
| (0.9,1.0] | 238 | 0.921 | 0.912 |

### over_1.5  (n=256)
| pred bin | n | mean pred | realized |
|---|---|---|---|
| (0.6,0.7] | 76 | 0.681 | 0.684 |
| (0.7,0.8] | 177 | 0.730 | 0.712 |
| (0.8,0.9] | 3 | 0.811 | 0.667 |

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
| (0.4,0.5] | 199 | 0.470 | 0.472 |
| (0.5,0.6] | 57 | 0.514 | 0.544 |
