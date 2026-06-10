"""
Audit country_value_history.parquet to diagnose:
  - Germany showing log_value ~ 0 (≤ €1) in 2018
  - Tiny territories (Cambodia, French Guiana, Guadeloupe) showing ~€62M
  - Pooled distribution with min=0, std=4.18 (bimodal smoking gun)

Run from project root:
    uv run python scripts/15_audit_value_history.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

vh = pd.read_parquet(PROCESSED_DIR / "country_value_history.parquet")

# ----------------------------------------------------------------------------
# 1. Schema & basic stats
# ----------------------------------------------------------------------------
print("=" * 72)
print("1. SCHEMA & BASIC STATS")
print("=" * 72)
print(f"Shape: {vh.shape}")
print(f"Columns: {list(vh.columns)}")
print(f"Dtypes:\n{vh.dtypes.to_string()}")
print(f"\nDate range: {vh['date'].min().date()} -> {vh['date'].max().date()}")
print(f"Unique countries: {vh['country'].nunique()}")

print(f"\ntop_n_mean_eur descriptive stats:")
print(vh["top_n_mean_eur"].describe().to_string())

print(f"\nValue pathology checks (raw EUR):")
print(f"  Exactly zero:   {(vh['top_n_mean_eur'] == 0).sum():>7,}")
print(f"  <= 1 EUR:       {(vh['top_n_mean_eur'] <= 1).sum():>7,}")
print(f"  NaN:            {vh['top_n_mean_eur'].isna().sum():>7,}")
print(f"  Negative:       {(vh['top_n_mean_eur'] < 0).sum():>7,}")

# Any extra columns the build script wrote (e.g. n_players)?
extra = [c for c in vh.columns if c not in ("country", "date", "top_n_mean_eur")]
if extra:
    print(f"\nExtra columns present: {extra}")
    for c in extra:
        print(f"\n  {c} stats:")
        print(vh[c].describe().to_string())

# ----------------------------------------------------------------------------
# 2. Country naming — confirm key teams are present, look for mismatches
# ----------------------------------------------------------------------------
print("\n" + "=" * 72)
print("2. COUNTRY NAMING / PRESENCE")
print("=" * 72)

cset = set(vh["country"].astype(str).unique())

check_names = [
    # Expected high
    "Germany", "Brazil", "France", "England", "Spain", "Argentina", "Belgium",
    "Netherlands", "Portugal", "Italy",
    # Diagnostic offenders (showed inflated values)
    "Cambodia", "Laos", "French Guiana", "Guadeloupe",
    "United States Virgin Islands", "US Virgin Islands", "Virgin Islands, U.S.",
    "Aruba", "Grenada", "Saint Vincent and the Grenadines", "Saint Martin",
    # Expected mid/low
    "Saudi Arabia", "Iran", "Australia", "Japan", "Mexico", "USA",
    "United States", "United States of America",
    # Mapping special cases
    "South Korea", "Korea, South", "Korea",
    "Ivory Coast", "Cote d'Ivoire", "Côte d'Ivoire",
    "Curacao", "Curaçao",
    "Bosnia and Herzegovina", "Bosnia-Herzegovina",
    # Sanity
    "Andorra", "Liechtenstein", "Russia",
]
for name in check_names:
    mark = "✓" if name in cset else "✗"
    print(f"  {mark} {name!r}")

print(f"\nFirst 30 country names alphabetically (eyeball for spelling oddities):")
for c in sorted(cset)[:30]:
    print(f"  {c}")

# ----------------------------------------------------------------------------
# 3. Full ranking at a fixed mid-history snapshot — the smoking gun
# ----------------------------------------------------------------------------
SNAPSHOT = pd.Timestamp("2018-06-01")
print("\n" + "=" * 72)
print(f"3. FULL RANKING AT {SNAPSHOT.date()}")
print("=" * 72)

snap = (
    vh[vh["date"] <= SNAPSHOT]
    .sort_values("date")
    .groupby("country", as_index=False)
    .tail(1)
    .copy()
)
snap["value_M"] = (snap["top_n_mean_eur"] / 1e6).round(3)
snap = snap.sort_values("top_n_mean_eur", ascending=False).reset_index(drop=True)

print(f"\nTop 30 by value at {SNAPSHOT.date()}:")
print(snap.head(30)[["country", "date", "value_M"]].to_string(index=False))

print(f"\nBottom 30 by value at {SNAPSHOT.date()}:")
print(snap.tail(30)[["country", "date", "value_M"]].to_string(index=False))

# Mid-tier for context
mid_idx = len(snap) // 2
print(f"\nMid-rank (around position {mid_idx}):")
print(snap.iloc[mid_idx - 5:mid_idx + 5][["country", "date", "value_M"]].to_string(index=False))

# ----------------------------------------------------------------------------
# 4. Per-country time series for the key teams
# ----------------------------------------------------------------------------
print("\n" + "=" * 72)
print("4. TIME SERIES FOR KEY COUNTRIES (June-1 snapshot each year)")
print("=" * 72)

key_countries = [
    "Germany", "Brazil", "France", "England", "Spain", "Argentina",
    "Cambodia", "Laos", "French Guiana", "Guadeloupe",
    "Saudi Arabia", "Andorra", "Liechtenstein",
]
years_of_interest = [2008, 2010, 2014, 2018, 2022, 2026]

for country in key_countries:
    sub = vh[vh["country"] == country].sort_values("date")
    if len(sub) == 0:
        print(f"\n{country}: NOT IN VH")
        continue
    print(f"\n{country}: {len(sub)} monthly rows, "
          f"{sub['date'].min().date()} -> {sub['date'].max().date()}")
    pieces = []
    for y in years_of_interest:
        target = pd.Timestamp(f"{y}-06-01")
        s = sub[sub["date"] <= target]
        if len(s) == 0:
            pieces.append(f"{y}=—")
        else:
            v = s.iloc[-1]["top_n_mean_eur"]
            pieces.append(f"{y}=€{v/1e6:.2f}M")
    print("  " + "  ".join(pieces))

# ----------------------------------------------------------------------------
# 5. Distribution histogram and outlier scan
# ----------------------------------------------------------------------------
print("\n" + "=" * 72)
print("5. VALUE DISTRIBUTION (all country-month observations)")
print("=" * 72)

buckets = [-np.inf, 0, 1, 1e5, 1e6, 5e6, 1e7, 2e7, 5e7, 1e8, np.inf]
labels = [
    "< 0", "= 0", "(0, 100K]", "(100K, 1M]", "(1M, 5M]", "(5M, 10M]",
    "(10M, 20M]", "(20M, 50M]", "(50M, 100M]", "> 100M",
]
counts = pd.cut(
    vh["top_n_mean_eur"], bins=buckets, include_lowest=True, labels=labels
).value_counts().reindex(labels)
print(f"\nObservation count by EUR bucket:")
for label, count in counts.items():
    pct = 100 * count / len(vh)
    bar = "█" * int(pct / 2)
    print(f"  {label:>14s}: {count:>6,} ({pct:5.2f}%) {bar}")

# Per-country max — find major teams with suspiciously low max and vice versa
maxes = vh.groupby("country")["top_n_mean_eur"].max().sort_values()

print("\nCountries whose all-time-max value is < €10M (suspect under-counted):")
low_max = maxes[maxes < 10e6]
print(f"  Total: {len(low_max)} countries")
for c, m in low_max.items():
    print(f"    {c:>40s}: €{m/1e6:6.2f}M")

print("\nCountries whose all-time-max value is > €30M (sanity check the top):")
high_max = maxes[maxes > 30e6].sort_values(ascending=False)
print(f"  Total: {len(high_max)} countries")
for c, m in high_max.items():
    print(f"    {c:>40s}: €{m/1e6:7.2f}M")