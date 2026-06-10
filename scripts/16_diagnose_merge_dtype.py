"""
Confirm the merge_asof bug is a StringDtype mismatch by:
  1. Printing the dtypes of both sides of the merge
  2. Doing a direct lookup for French Guiana 2018-10-11 in vh
  3. Doing the actual merge_asof and pulling the same row
  4. Repeating with .astype(object) on both sides as a control
"""
from pathlib import Path
import numpy as np
import pandas as pd

from wc2026.features.squad_values import TEAM_TO_TM_COUNTRY

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"

results = pd.read_parquet(PROCESSED / "results.parquet")
vh = pd.read_parquet(PROCESSED / "country_value_history.parquet")

# Replicate left side
played = (
    results.dropna(subset=["home_score", "away_score"])
    .pipe(lambda d: d[(d["date"] >= "2000-01-01") & (d["date"] <= "2026-06-10")])
    .sort_values("date")
    .reset_index(drop=True)
    .copy()
)

print("=" * 72)
print("DTYPE TRACE")
print("=" * 72)
print(f"played['home_team'].dtype:        {played['home_team'].dtype}")
print(f"vh['country'].dtype:              {vh['country'].dtype}")

def _to_tm(n): return TEAM_TO_TM_COUNTRY.get(n, n)
home_tm_strcast = played["home_team"].map(_to_tm).astype(str)
home_tm_objcast = played["home_team"].map(_to_tm).astype(object)
vh_str = vh["country"].astype(str)
vh_obj = vh["country"].astype(object)

print(f"\nLeft side after .astype(str):     {home_tm_strcast.dtype}")
print(f"Left side after .astype(object):  {home_tm_objcast.dtype}")
print(f"Right vh after .astype(str):      {vh_str.dtype}")
print(f"Right vh after .astype(object):   {vh_obj.dtype}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("GROUND TRUTH FOR FRENCH GUIANA AT 2018-10-11")
print("=" * 72)
fg = vh[vh["country"] == "French Guiana"].sort_values("date")
fg_pretarget = fg[fg["date"] <= pd.Timestamp("2018-10-11")].tail(1)
print(fg_pretarget[["country", "date", "top_n_mean_eur"]].to_string(index=False))
truth_log = np.log(max(fg_pretarget["top_n_mean_eur"].iloc[0], 1.0))
print(f"Expected log_value: {truth_log:.4f}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("MERGE A: current code (.astype(str) on both sides)")
print("=" * 72)
vh_a = vh[["country", "date", "top_n_mean_eur"]].copy()
vh_a["country"] = vh_a["country"].astype(str)
vh_a["log_value"] = np.log(vh_a["top_n_mean_eur"].clip(lower=1.0))
left_a = played[["date"]].assign(country=home_tm_strcast).sort_values("date")
res_a = pd.merge_asof(
    left_a, vh_a[["country", "date", "log_value"]].sort_values("date"),
    on="date", by="country", direction="backward", allow_exact_matches=True,
)
mask = (played["date"] == "2018-10-11") & (played["home_team"] == "French Guiana")
print(f"Returned log_value: {res_a.loc[mask.values, 'log_value'].values}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("MERGE B: forced object dtype on both sides")
print("=" * 72)
vh_b = vh[["country", "date", "top_n_mean_eur"]].copy()
vh_b["country"] = vh_b["country"].astype(object)
vh_b["log_value"] = np.log(vh_b["top_n_mean_eur"].clip(lower=1.0))
left_b = played[["date"]].assign(country=home_tm_objcast).sort_values("date")
res_b = pd.merge_asof(
    left_b, vh_b[["country", "date", "log_value"]].sort_values("date"),
    on="date", by="country", direction="backward", allow_exact_matches=True,
)
print(f"Returned log_value: {res_b.loc[mask.values, 'log_value'].values}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("MERGE C: exact merge on (country, year_month)")
print("=" * 72)

vh_c = vh[["country", "date", "top_n_mean_eur"]].copy()
vh_c["country"] = vh_c["country"].astype(object)
vh_c["ym"] = (vh_c["date"].dt.year * 100 + vh_c["date"].dt.month).astype("int64")
vh_c["log_value"] = np.log(vh_c["top_n_mean_eur"].clip(lower=1.0))

left_c = pd.DataFrame({
    "country": played["home_team"].map(_to_tm).astype(object),
    "ym": (played["date"].dt.year * 100 + played["date"].dt.month).astype("int64"),
})
res_c = left_c.merge(vh_c[["country", "ym", "log_value"]], on=["country", "ym"], how="left")
print(f"Returned log_value for French Guiana 2018-10-11: "
      f"{res_c.loc[mask.values, 'log_value'].values}")
print(f"(Expected: {truth_log:.4f})")