"""
Compute population-weighted monthly HDD and CDD for each EIA entity.

Also computes the 2016-2024 calendar-month normal (mean over all years for
each month) used later as the "replace actual with normal" step.

Output: data/entity_hddcdd_monthly.parquet
  Columns: entity, year, month, hdd, cdd

        data/entity_hddcdd_normals.parquet
  Columns: entity, month, hdd_normal, cdd_normal
"""

import pandas as pd
import numpy as np
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"

# ── Load inputs ───────────────────────────────────────────────────────────
print("Loading inputs...")
weights = pd.read_parquet(OUT_DIR / "entity_climdiv_weights.parquet")
hdd_raw = pd.read_parquet(OUT_DIR / "nclimdiv_hdd_monthly.parquet")
cdd_raw = pd.read_parquet(OUT_DIR / "nclimdiv_cdd_monthly.parquet")

# Rename for merge clarity
hdd_raw = hdd_raw.rename(columns={"value": "hdd"})
cdd_raw = cdd_raw.rename(columns={"value": "cdd"})

# state_fips and div_num types must match weights
for df in [hdd_raw, cdd_raw]:
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["div_num"]    = df["div_num"].astype(int)

weights["state_fips"] = weights["state_fips"].astype(str).str.zfill(2)
weights["div_num"]    = weights["div_num"].astype(int)

print(f"  Entities in crosswalk: {weights['entity'].nunique()}")

# ── Merge HDD/CDD onto weights ────────────────────────────────────────────
hdd_merged = weights.merge(hdd_raw, on=["state_fips", "div_num"], how="left")
cdd_merged = weights.merge(cdd_raw, on=["state_fips", "div_num"], how="left")

# ── Weighted average per entity-year-month ────────────────────────────────
def weighted_avg(merged_df, value_col):
    merged_df = merged_df.copy()
    merged_df["weighted"] = merged_df[value_col] * merged_df["pop_weight"]
    # Sum of weighted values; NaN if all divisions missing
    result = (
        merged_df.groupby(["entity", "year", "month"])
        .agg(
            value=("weighted", "sum"),
            weight_sum=("pop_weight", lambda x: x[merged_df.loc[x.index, value_col].notna()].sum())
        )
        .reset_index()
    )
    # Re-normalize: divide by sum of weights that had valid data
    # (handles cases where some divisions have missing values)
    result["value"] = result["value"] / result["weight_sum"].clip(lower=1e-9)
    result.loc[result["weight_sum"] < 0.1, "value"] = np.nan  # < 10% coverage → missing
    return result.drop(columns="weight_sum")

print("Computing weighted HDD...")
hdd_entity = weighted_avg(hdd_merged, "hdd").rename(columns={"value": "hdd"})
print("Computing weighted CDD...")
cdd_entity = weighted_avg(cdd_merged, "cdd").rename(columns={"value": "cdd"})

entity_df = hdd_entity.merge(cdd_entity, on=["entity", "year", "month"], how="outer")
entity_df = entity_df.sort_values(["entity", "year", "month"]).reset_index(drop=True)

out_path = OUT_DIR / "entity_hddcdd_monthly.parquet"
entity_df.to_parquet(out_path, index=False)
print(f"Saved {len(entity_df):,} rows → {out_path.name}")

# ── Compute normals: mean HDD/CDD per entity-month over 2016-2024 ─────────
norm_df = (
    entity_df[(entity_df["year"] >= 2016) & (entity_df["year"] <= 2024)]
    .groupby(["entity", "month"])
    .agg(hdd_normal=("hdd", "mean"), cdd_normal=("cdd", "mean"))
    .reset_index()
)
norm_path = OUT_DIR / "entity_hddcdd_normals.parquet"
norm_df.to_parquet(norm_path, index=False)
print(f"Saved {len(norm_df):,} rows → {norm_path.name}")

# ── Quick sanity check ────────────────────────────────────────────────────
print("\n--- Sample: CISO (California) HDD/CDD 2021 ---")
sample = entity_df[(entity_df["entity"] == "CISO") & (entity_df["year"] == 2021)]
print(sample.to_string(index=False))

print("\n--- Normals for selected entities (month=7, July) ---")
jul = norm_df[norm_df["month"] == 7].sort_values("cdd_normal", ascending=False)
print(jul.head(10).to_string(index=False))
