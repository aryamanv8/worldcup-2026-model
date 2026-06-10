"""
Verify the squad value merge in the new training matrix.

Checks:
 1. New columns exist and have expected dtypes.
 2. NaN counts (rows we'll lose to dropna in prepare_design_matrix).
 3. Distribution of log_value — gives us the z-score constants for poisson.py.
 4. Spot-checks: top/bottom teams in 2018, pre-2008 backfill behavior.
 5. has_actual_value distribution across time.

Run:
    uv run python scripts/14_verify_value_merge.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

tm = pd.read_parquet(PROCESSED_DIR / "training_matrix.parquet")
print(f"Training matrix: {len(tm):,} matches, "
      f"{tm['date'].min().date()} -> {tm['date'].max().date()}")

# --- 1. Schema check ---
new_cols = [
    "home_value_log_eur", "away_value_log_eur",
    "home_has_actual_value", "away_has_actual_value",
]
print("\n[1] New columns present?")
for c in new_cols:
    if c in tm.columns:
        print(f"  ✓ {c}  dtype={tm[c].dtype}")
    else:
        print(f"  ✗ MISSING: {c}")

# --- 2. NaN counts ---
print("\n[2] NaN counts (these rows will be dropped at design-matrix time):")
for c in ["home_value_log_eur", "away_value_log_eur"]:
    n_nan = tm[c].isna().sum()
    print(f"  {c}: {n_nan:,} NaN ({100*n_nan/len(tm):.2f}%)")

# --- 3. Log-value distribution (z-score constants for poisson.py) ---
log_vals = pd.concat([tm["home_value_log_eur"], tm["away_value_log_eur"]]).dropna()
mu, sd = log_vals.mean(), log_vals.std()
print(f"\n[3] log(top_n_mean_eur) pooled distribution:")
print(f"  mean={mu:.4f}  std={sd:.4f}  "
      f"min={log_vals.min():.2f}  max={log_vals.max():.2f}")
print(f"  -> These are the z-score constants to hardcode in poisson.py")

# --- 4. Spot-checks ---
print("\n[4a] Highest-value team-matches in 2018:")
m2018 = tm[(tm["date"] >= "2018-01-01") & (tm["date"] < "2019-01-01")]
top = m2018.nlargest(5, "home_value_log_eur")[
    ["date", "home_team", "away_team", "home_value_log_eur", "home_has_actual_value"]
]
print(top.to_string(index=False))

print("\n[4b] Lowest-value team-matches in 2018:")
bot = m2018.nsmallest(5, "home_value_log_eur")[
    ["date", "home_team", "away_team", "home_value_log_eur", "home_has_actual_value"]
]
print(bot.to_string(index=False))

print("\n[4c] Sample of pre-2008 matches (should show has_actual_value=0):")
pre = tm[tm["date"] < "2008-01-01"].sample(min(5, len(tm[tm['date'] < '2008-01-01'])), random_state=0)[
    ["date", "home_team", "away_team",
     "home_value_log_eur", "home_has_actual_value",
     "away_value_log_eur", "away_has_actual_value"]
]
print(pre.to_string(index=False))

# --- 5. has_actual_value over time ---
print("\n[5] has_actual_value rate by year (home side):")
yearly = tm.assign(year=tm["date"].dt.year).groupby("year")[
    "home_has_actual_value"
].agg(["mean", "count"])
print(yearly.to_string())