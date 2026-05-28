"""
Fit per-entity log-OLS weather regression and apply monthly normalization.

Regression (fit once per entity on all available monthly data):
  log(monthly_MWh) ~ HDD + CDD + HDD² + CDD²
                   + month fixed effects (dummies, Jan omitted)
                   + year linear trend

Normalization (applied month by month):
  norm_factor_t = exp(β_HDD*(HDD_normal - HDD_t) + β_CDD*(CDD_normal - CDD_t)
                    + β_HDD²*(HDD_normal² - HDD_t²) + β_CDD²*(CDD_normal² - CDD_t²))

  normalized_MWh_t = actual_MWh_t × norm_factor_t
  normalized_hourly_MW_t = actual_MW_t × norm_factor_t  (same factor for all hours in month)

Outputs:
  data/regression_diagnostics.csv        — R², coefficients, N per entity
  data/monthly_normalized_regions.parquet
  data/monthly_normalized_subregions.parquet
  data/hourly_normalized_regions.parquet
  data/hourly_normalized_subregions.parquet
"""

import warnings
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"
warnings.filterwarnings("ignore")


def fit_and_normalize(monthly: pd.DataFrame,
                      hddcdd:  pd.DataFrame,
                      normals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    For each entity in monthly, fit regression and compute norm_factor.
    Returns (monthly_with_norm, diagnostics_df).
    """
    monthly  = monthly.copy()
    hddcdd   = hddcdd.copy()
    normals  = normals.copy()

    # Merge weather onto monthly demand
    df = monthly.merge(hddcdd,  on=["entity", "year", "month"], how="left")
    df = df.merge(normals[["entity", "month", "hdd_normal", "cdd_normal"]],
                  on=["entity", "month"], how="left")

    df["hdd2"] = df["hdd"] ** 2
    df["cdd2"] = df["cdd"] ** 2
    df["log_mwh"] = np.log(df["mwh_total"].clip(lower=1))
    df["month_str"] = df["month"].astype(str).str.zfill(2)

    diag_rows = []
    norm_factors = {}

    for entity, grp in df.groupby("entity"):
        grp = grp.dropna(subset=["log_mwh", "hdd", "cdd"])
        if len(grp) < 12:
            diag_rows.append({"entity": entity, "n": len(grp), "r2": np.nan,
                               "b_hdd": np.nan, "b_cdd": np.nan, "note": "too_few_obs"})
            norm_factors[entity] = pd.Series(np.nan, index=grp.index)
            continue

        try:
            formula = ("log_mwh ~ hdd + cdd + hdd2 + cdd2 "
                       "+ C(month_str) + year")
            model  = smf.ols(formula, data=grp).fit()
            r2     = model.rsquared
            b_hdd  = model.params.get("hdd", np.nan)
            b_hdd2 = model.params.get("hdd2", np.nan)
            b_cdd  = model.params.get("cdd", np.nan)
            b_cdd2 = model.params.get("cdd2", np.nan)

            # Compute log-scale weather anomaly: log(pred_at_normal) - log(pred_at_actual)
            grp2 = grp.copy()
            grp2["delta_log"] = (
                b_hdd  * (grp2["hdd_normal"] - grp2["hdd"])
              + b_hdd2 * (grp2["hdd_normal"] ** 2 - grp2["hdd2"])
              + b_cdd  * (grp2["cdd_normal"] - grp2["cdd"])
              + b_cdd2 * (grp2["cdd_normal"] ** 2 - grp2["cdd2"])
            )
            norm_factors[entity] = np.exp(grp2.set_index(grp2.index)["delta_log"])

            diag_rows.append({"entity": entity, "n": len(grp), "r2": round(r2, 4),
                               "b_hdd": round(b_hdd, 6), "b_cdd": round(b_cdd, 6),
                               "note": "ok"})
        except Exception as e:
            diag_rows.append({"entity": entity, "n": len(grp), "r2": np.nan,
                               "b_hdd": np.nan, "b_cdd": np.nan, "note": str(e)[:60]})
            norm_factors[entity] = pd.Series(np.nan, index=grp.index)

    # Attach norm_factor back to df
    df["norm_factor"] = pd.concat(norm_factors.values(), axis=0)
    df["mwh_normalized"] = df["mwh_total"] * df["norm_factor"]

    diagnostics = pd.DataFrame(diag_rows)
    return df, diagnostics


# ── Regions ──────────────────────────────────────────────────────────────
print("=== Regions ===")
monthly_r  = pd.read_parquet(OUT_DIR / "monthly_demand_regions.parquet")
hddcdd_all = pd.read_parquet(OUT_DIR / "entity_hddcdd_monthly.parquet")
normals    = pd.read_parquet(OUT_DIR / "entity_hddcdd_normals.parquet")
hourly_r   = pd.read_parquet(OUT_DIR / "hourly_demand_regions.parquet")

monthly_r_norm, diag_r = fit_and_normalize(monthly_r, hddcdd_all, normals)
print(f"  Entities fitted: {len(diag_r)}")
print(diag_r.to_string(index=False))

# Apply monthly norm factor to hourly data
hourly_r["year"]  = hourly_r["date_time"].dt.year
hourly_r["month"] = hourly_r["date_time"].dt.month
hourly_r = hourly_r.merge(
    monthly_r_norm[["entity", "year", "month", "norm_factor"]],
    on=["entity", "year", "month"], how="left"
)
hourly_r["demand_mw_normalized"] = hourly_r["demand"] * hourly_r["norm_factor"]
hourly_r = hourly_r.drop(columns=["year", "month"])

monthly_r_norm.to_parquet(OUT_DIR / "monthly_normalized_regions.parquet", index=False)
hourly_r      .to_parquet(OUT_DIR / "hourly_normalized_regions.parquet",  index=False)
print(f"  → saved monthly + hourly normalized regions\n")

# ── Sub-regions ───────────────────────────────────────────────────────────
print("=== Sub-regions ===")
monthly_s = pd.read_parquet(OUT_DIR / "monthly_demand_subregions.parquet")
hourly_s  = pd.read_parquet(OUT_DIR / "hourly_demand_subregions.parquet")

monthly_s_norm, diag_s = fit_and_normalize(monthly_s, hddcdd_all, normals)
print(f"  Entities fitted: {len(diag_s)}")

# Flag low-R² entities
low_r2 = diag_s[diag_s["r2"] < 0.5]
if not low_r2.empty:
    print("\n  ** Low R² entities (< 0.5) — weather explains little of their variance:")
    print(low_r2.to_string(index=False))

hourly_s["year"]  = hourly_s["date_time"].dt.year
hourly_s["month"] = hourly_s["date_time"].dt.month
hourly_s = hourly_s.merge(
    monthly_s_norm[["entity", "year", "month", "norm_factor"]],
    on=["entity", "year", "month"], how="left"
)
hourly_s["demand_mw_normalized"] = hourly_s["demand"] * hourly_s["norm_factor"]
hourly_s = hourly_s.drop(columns=["year", "month"])

monthly_s_norm.to_parquet(OUT_DIR / "monthly_normalized_subregions.parquet", index=False)
hourly_s      .to_parquet(OUT_DIR / "hourly_normalized_subregions.parquet",  index=False)

# ── Combined diagnostics ──────────────────────────────────────────────────
diag_r["dataset"] = "regions"
diag_s["dataset"] = "subregions"
diag_all = pd.concat([diag_r, diag_s], ignore_index=True)
diag_all.to_csv(OUT_DIR / "regression_diagnostics.csv", index=False)
print(f"\nAll diagnostics → {OUT_DIR / 'regression_diagnostics.csv'}")
print(f"Median R² regions:     {diag_r['r2'].median():.3f}")
print(f"Median R² sub-regions: {diag_s['r2'].median():.3f}")
