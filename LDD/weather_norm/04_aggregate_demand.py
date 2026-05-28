"""
Load EIA cleaned hourly demand, splice Release 1 (2016–2019) and
Release 2 (2020–2024), aggregate to monthly totals with QC, and
write one parquet per dataset type (regions / subregions).

QC rule: a month is flagged as low-coverage if > 3% of hours are missing
(~22 hrs/month). Those months get NaN demand in the monthly aggregate.

Output:
  data/monthly_demand_regions.parquet     (entities × year-month)
  data/monthly_demand_subregions.parquet
  data/hourly_demand_regions.parquet      (raw hourly, for scaling output later)
  data/hourly_demand_subregions.parquet

Monthly columns: entity, year, month, mwh_total, hours_valid, coverage
Hourly columns:  entity, date_time (UTC), demand_mw
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path

OUT_DIR  = Path(__file__).parent / "data"
BASE_LDD = Path(__file__).parent.parent / "EIA_Cleaned_Hourly_Electricity_Demand_Data" / "data"

R1_REGIONS  = BASE_LDD / "release_2020_Oct" / "regions"
R2_REGIONS  = BASE_LDD / "release_2025_Jan_include_subregions" / "regions"
R2_SUBS     = BASE_LDD / "release_2025_Jan_include_subregions" / "subregions_and_balancing_authorities"

# The 13 EIA regions (present in both releases)
REGIONS = ["CAL","CAR","CENT","FLA","MIDA","MIDW","NE","NW","NY","SE","SW","TEN","TEX"]


def load_entity_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date_time"])
    df = df.rename(columns={"cleaned demand (MW)": "demand"})
    df["demand"] = pd.to_numeric(df["demand"], errors="coerce")
    if "category" in df.columns:
        df.loc[df["category"] == "MISSING", "demand"] = np.nan
    df = df[["date_time", "demand"]].dropna(subset=["date_time"])
    df["date_time"] = df["date_time"].dt.tz_localize(None)   # strip tz, keep UTC-implicit
    return df.sort_values("date_time").reset_index(drop=True)


def splice_region(entity: str) -> pd.DataFrame:
    """Return hourly demand for a region, splicing R1 (2016-2019) + R2 (2020-2024)."""
    r1_path = R1_REGIONS / f"{entity}.csv"
    r2_path = R2_REGIONS / f"{entity}.csv"

    parts = []
    if r1_path.exists():
        r1 = load_entity_csv(r1_path)
        r1 = r1[(r1["date_time"].dt.year >= 2016) & (r1["date_time"].dt.year <= 2019)]
        parts.append(r1)
    if r2_path.exists():
        r2 = load_entity_csv(r2_path)
        r2 = r2[(r2["date_time"].dt.year >= 2020) & (r2["date_time"].dt.year <= 2024)]
        parts.append(r2)

    if not parts:
        return pd.DataFrame(columns=["date_time", "demand"])
    df = pd.concat(parts, ignore_index=True).drop_duplicates("date_time").sort_values("date_time")
    df["entity"] = entity
    return df.reset_index(drop=True)


def load_subregion(entity: str) -> pd.DataFrame:
    """Return hourly demand for a sub-region (R2 only, 2020-2024)."""
    path = R2_SUBS / f"{entity}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date_time", "demand"])
    df = load_entity_csv(path)
    df = df[(df["date_time"].dt.year >= 2020) & (df["date_time"].dt.year <= 2024)]
    df["entity"] = entity
    return df.reset_index(drop=True)


def to_monthly(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly demand to monthly; flag low-coverage months."""
    hourly_df = hourly_df.copy()
    hourly_df["year"]  = hourly_df["date_time"].dt.year
    hourly_df["month"] = hourly_df["date_time"].dt.month

    agg = (
        hourly_df.groupby(["entity", "year", "month"])
        .agg(
            mwh_total    =("demand", lambda x: x.sum(skipna=True)),
            hours_valid  =("demand", lambda x: x.notna().sum()),
            hours_total  =("demand", "count"),
        )
        .reset_index()
    )
    agg["coverage"] = agg["hours_valid"] / agg["hours_total"].clip(lower=1)
    # Zero out months with <97% valid hours
    agg.loc[agg["coverage"] < 0.97, "mwh_total"] = np.nan
    return agg.drop(columns="hours_total")


# ── Process regions ───────────────────────────────────────────────────────
print("Processing regions...")
region_hourly_parts = []
region_monthly_parts = []

for entity in REGIONS:
    print(f"  {entity}", end="", flush=True)
    h = splice_region(entity)
    if h.empty:
        print(" MISSING")
        continue
    print(f" {len(h):,} hrs")
    region_hourly_parts.append(h)
    region_monthly_parts.append(to_monthly(h))

region_hourly  = pd.concat(region_hourly_parts,  ignore_index=True)
region_monthly = pd.concat(region_monthly_parts, ignore_index=True)
region_hourly .to_parquet(OUT_DIR / "hourly_demand_regions.parquet",  index=False)
region_monthly.to_parquet(OUT_DIR / "monthly_demand_regions.parquet", index=False)
print(f"Regions: {len(region_monthly):,} entity-months")

# ── Process sub-regions ───────────────────────────────────────────────────
print("\nProcessing sub-regions (R2 parent BAs + sub-region splits)...")
# Everything in R2 subs dir that isn't one of the 13 regions and isn't a region file
sub_files = [f.stem for f in sorted(R2_SUBS.glob("*.csv"))]
# Sub-regions = files with a dash; parent BAs = files without
parent_bas  = [f for f in sub_files if "-" not in f]
sub_regions = [f for f in sub_files if "-" in f]
all_subs = parent_bas + sub_regions

sub_hourly_parts   = []
sub_monthly_parts  = []

for entity in all_subs:
    print(f"  {entity}", end="", flush=True)
    h = load_subregion(entity)
    if h.empty:
        print(" MISSING")
        continue
    print(f" {len(h):,} hrs")
    sub_hourly_parts.append(h)
    sub_monthly_parts.append(to_monthly(h))

sub_hourly  = pd.concat(sub_hourly_parts,  ignore_index=True)
sub_monthly = pd.concat(sub_monthly_parts, ignore_index=True)
sub_hourly .to_parquet(OUT_DIR / "hourly_demand_subregions.parquet",  index=False)
sub_monthly.to_parquet(OUT_DIR / "monthly_demand_subregions.parquet", index=False)
print(f"Sub-regions: {len(sub_monthly):,} entity-months")

# ── Splice validation: R1 vs R2 overlap for regions ──────────────────────
print("\n--- Splice validation (Jan–Jul 2020 overlap) ---")
for entity in REGIONS[:5]:
    r1_path = R1_REGIONS / f"{entity}.csv"
    r2_path = R2_REGIONS / f"{entity}.csv"
    if not (r1_path.exists() and r2_path.exists()):
        continue
    r1 = load_entity_csv(r1_path)
    r2 = load_entity_csv(r2_path)
    overlap_r1 = r1[(r1["date_time"].dt.year == 2020) & (r1["date_time"].dt.month.isin([1,2,3,4,5,6]))]["demand"].mean()
    overlap_r2 = r2[(r2["date_time"].dt.year == 2020) & (r2["date_time"].dt.month.isin([1,2,3,4,5,6]))]["demand"].mean()
    pct_diff = abs(overlap_r1 - overlap_r2) / overlap_r2 * 100
    flag = " *** LARGE DIFF" if pct_diff > 5 else ""
    print(f"  {entity}: R1={overlap_r1:.0f} MW  R2={overlap_r2:.0f} MW  diff={pct_diff:.1f}%{flag}")
