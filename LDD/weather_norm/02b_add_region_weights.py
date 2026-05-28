"""
Add the 13 EIA region codes to entity_climdiv_weights.parquet.

EIA 930 regions don't have dedicated shapefiles, so we build their
climate-division weights from a state-FIPS composition list. Each region's
weight = population-weighted sum of climate divisions in its constituent states.

State-to-region mapping follows EIA 930 planning area definitions.
"""

import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"

# State FIPS (Census) → EIA region
# Some states straddle regions; assigned to dominant-load region.
STATE_TO_REGION = {
    "06": "CAL",   # California
    "37": "CAR",   # North Carolina
    "45": "CAR",   # South Carolina
    "05": "CENT",  # Arkansas
    "20": "CENT",  # Kansas
    "22": "CENT",  # Louisiana   (southern MISO / SPP)
    "29": "CENT",  # Missouri
    "31": "CENT",  # Nebraska
    "40": "CENT",  # Oklahoma
    "46": "CENT",  # South Dakota
    "12": "FLA",   # Florida
    "10": "MIDA",  # Delaware
    "11": "MIDA",  # DC
    "24": "MIDA",  # Maryland
    "34": "MIDA",  # New Jersey
    "39": "MIDA",  # Ohio
    "42": "MIDA",  # Pennsylvania
    "51": "MIDA",  # Virginia
    "54": "MIDA",  # West Virginia
    "17": "MIDW",  # Illinois
    "18": "MIDW",  # Indiana
    "19": "MIDW",  # Iowa
    "26": "MIDW",  # Michigan
    "27": "MIDW",  # Minnesota
    "28": "MIDW",  # Mississippi  (MISO south)
    "55": "MIDW",  # Wisconsin
    "09": "NE",    # Connecticut
    "23": "NE",    # Maine
    "25": "NE",    # Massachusetts
    "33": "NE",    # New Hampshire
    "44": "NE",    # Rhode Island
    "50": "NE",    # Vermont
    "16": "NW",    # Idaho
    "30": "NW",    # Montana
    "38": "NW",    # North Dakota
    "41": "NW",    # Oregon
    "53": "NW",    # Washington
    "56": "NW",    # Wyoming
    "36": "NY",    # New York
    "01": "SE",    # Alabama
    "13": "SE",    # Georgia
    "04": "SW",    # Arizona
    "08": "SW",    # Colorado
    "32": "SW",    # Nevada
    "35": "SW",    # New Mexico
    "49": "SW",    # Utah
    "21": "TEN",   # Kentucky
    "47": "TEN",   # Tennessee
    "48": "TEX",   # Texas
}

# ── Load county → climate division crosswalk + population ────────────────
print("Loading crosswalk inputs...")

# Re-use the county population + climdiv crosswalk already built in 02_build_crosswalk.py
# (those files were cached; faster than re-downloading)
import requests, io

# County population
pop_df = pd.read_csv(
    OUT_DIR / "cache" / "co-est2023-alldata.csv",
    encoding="latin1", dtype=str
)
pop_df = pop_df[pop_df["SUMLEV"] == "050"].copy()
pop_df["fips5"]      = pop_df["STATE"].str.zfill(2) + pop_df["COUNTY"].str.zfill(3)
pop_df["state_fips_census"] = pop_df["STATE"].str.zfill(2)
pop_df["population"] = pd.to_numeric(pop_df["POPESTIMATE2020"], errors="coerce").fillna(0)
pop_df = pop_df[["fips5", "state_fips_census", "population"]]

# County → nClimDiv crosswalk
r = requests.get("https://www.ncei.noaa.gov/pub/data/cirs/climdiv/county-to-climdivs.txt", timeout=30)
lines = [l for l in r.text.splitlines() if l and l[0].isdigit()]
xwalk = pd.DataFrame([l.split() for l in lines], columns=["postal_fips", "ncdc_fips", "climdiv_id"])
xwalk["fips5"]      = xwalk["postal_fips"].str.zfill(5)
xwalk["state_fips"] = xwalk["climdiv_id"].str[:2]   # nClimDiv state code
xwalk["div_num"]    = xwalk["climdiv_id"].str[2:].astype(int)

# Merge population + xwalk on county FIPS
county_df = pop_df.merge(xwalk[["fips5", "state_fips", "div_num"]], on="fips5", how="left")
county_df = county_df.dropna(subset=["div_num"])
county_df["div_num"] = county_df["div_num"].astype(int)

# ── Map counties → EIA regions via census state FIPS ────────────────────
county_df["region"] = county_df["state_fips_census"].map(STATE_TO_REGION)
county_df = county_df.dropna(subset=["region"])

region_divs = (
    county_df.groupby(["region", "state_fips", "div_num"])["population"]
    .sum()
    .reset_index()
)
totals = region_divs.groupby("region")["population"].transform("sum")
region_divs["pop_weight"] = region_divs["population"] / totals.clip(lower=1)
region_divs = region_divs.rename(columns={"region": "entity"}).drop(columns="population")

print("\nRegions built:")
for r, g in region_divs.groupby("entity"):
    print(f"  {r:<6} {len(g)} climate divisions, top state weight: "
          f"{g.groupby('state_fips')['pop_weight'].sum().max():.2f}")

# ── Append to existing crosswalk ─────────────────────────────────────────
existing = pd.read_parquet(OUT_DIR / "entity_climdiv_weights.parquet")
# Drop any existing region entries (re-run safe)
existing = existing[~existing["entity"].isin(region_divs["entity"].unique())]
combined = pd.concat([existing, region_divs], ignore_index=True)
combined.to_parquet(OUT_DIR / "entity_climdiv_weights.parquet", index=False)
print(f"\nUpdated crosswalk: {combined['entity'].nunique()} entities total")
