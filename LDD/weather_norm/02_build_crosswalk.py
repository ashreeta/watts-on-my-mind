"""
Build crosswalk: EIA entity → dominant state → population-weighted climate divisions.

For parent BAs: use BA polygon from GeoJSON, intersect with Census county centroids,
weight by county population, pick state with largest population share.

For sub-regions (CISO-*, ERCO-*, NYIS-*, etc.): manual state mapping since
sub-region polygons are not in the GeoJSON.

Output: data/entity_climdiv_weights.parquet
  Columns: entity, state_fips, div_num, pop_weight
  (pop_weight sums to 1.0 per entity; one row per climate division contributing)
"""

import io, zipfile, os, requests
import pandas as pd
import geopandas as gpd
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"
CACHE   = OUT_DIR / "cache"
CACHE.mkdir(exist_ok=True)

GEO_BA = Path(__file__).parent.parent / "ba_boundaries_simplified.geojson"

# ── 1. Load BA boundaries ──────────────────────────────────────────────────
print("Loading BA boundaries...")
ba_gdf = gpd.read_file(GEO_BA)[["BA_CODE", "geometry"]].copy()
ba_gdf = ba_gdf[ba_gdf["BA_CODE"].notna() & (ba_gdf["BA_CODE"] != "")]
ba_gdf = ba_gdf.to_crs("EPSG:4326")

# ── 2. Download Census TIGER counties (centroids) ─────────────────────────
county_zip = CACHE / "cb_2021_us_county_500k.zip"
if not county_zip.exists():
    print("Downloading Census TIGER county shapefile (~12 MB)...")
    r = requests.get(
        "https://www2.census.gov/geo/tiger/GENZ2021/shp/cb_2021_us_county_500k.zip",
        timeout=120
    )
    r.raise_for_status()
    county_zip.write_bytes(r.content)
    print("  saved.")

print("Loading county shapefile...")
county_gdf = gpd.read_file(f"zip://{county_zip}").to_crs("EPSG:4326")
# STATEFP + COUNTYFP → 5-digit FIPS
county_gdf["fips5"] = county_gdf["STATEFP"] + county_gdf["COUNTYFP"]
# Exclude non-CONUS territories (keep only 50 states + DC)
conus_state_fips = {f"{i:02d}" for i in range(1, 57) if i not in (3, 7, 14, 43, 52)}
county_gdf = county_gdf[county_gdf["STATEFP"].isin(conus_state_fips)].copy()
county_gdf["centroid"] = county_gdf.geometry.centroid

# ── 3. Census county populations (no API key needed) ─────────────────────
pop_csv = CACHE / "co-est2023-alldata.csv"
if not pop_csv.exists():
    print("Downloading Census county population estimates...")
    r = requests.get(
        "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv",
        timeout=60
    )
    r.raise_for_status()
    pop_csv.write_bytes(r.content)

pop_df = pd.read_csv(pop_csv, encoding="latin1", dtype=str)
# SUMLEV 050 = county
pop_df = pop_df[pop_df["SUMLEV"] == "050"].copy()
pop_df["fips5"] = pop_df["STATE"].str.zfill(2) + pop_df["COUNTY"].str.zfill(3)
pop_df["population"] = pd.to_numeric(pop_df["POPESTIMATE2020"], errors="coerce").fillna(0)
pop_df = pop_df[["fips5", "population"]]

county_gdf = county_gdf.merge(pop_df, on="fips5", how="left")
county_gdf["population"] = county_gdf["population"].fillna(0)

# ── 4. nClimDiv county → climate division crosswalk ──────────────────────
print("Loading nClimDiv county-to-division crosswalk...")
xwalk_url = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/county-to-climdivs.txt"
r = requests.get(xwalk_url, timeout=30)
r.raise_for_status()
lines = [l for l in r.text.splitlines() if l and l[0].isdigit()]
xwalk = pd.DataFrame([l.split() for l in lines],
                     columns=["postal_fips", "ncdc_fips", "climdiv_id"])
xwalk["fips5"] = xwalk["postal_fips"].str.zfill(5)
xwalk["state_fips"] = xwalk["climdiv_id"].str[:2]
xwalk["div_num"]    = xwalk["climdiv_id"].str[2:].astype(int)
xwalk = xwalk[["fips5", "state_fips", "div_num"]]

county_gdf = county_gdf.merge(xwalk, on="fips5", how="left")

# ── 5. Point-in-polygon: assign counties to parent BAs ───────────────────
print("Running point-in-polygon for parent BAs...")
# Build points GeoDataFrame from county centroids
pts = gpd.GeoDataFrame(
    county_gdf[["fips5", "STATEFP", "population", "state_fips", "div_num"]].copy(),
    geometry=county_gdf["centroid"],
    crs="EPSG:4326"
)

joined = gpd.sjoin(pts, ba_gdf[["BA_CODE", "geometry"]], how="left", predicate="within")
joined = joined.dropna(subset=["BA_CODE"])

# Population share per (BA_CODE, state_fips, div_num)
ba_divs = (
    joined.groupby(["BA_CODE", "state_fips", "div_num"])["population"]
    .sum()
    .reset_index()
)

# Dominant state per BA (for reference)
state_pop = (
    joined.groupby(["BA_CODE", "STATEFP"])["population"]
    .sum()
    .reset_index()
)
state_pop["rank"] = state_pop.groupby("BA_CODE")["population"].rank(ascending=False)
dominant_state = state_pop[state_pop["rank"] == 1][["BA_CODE", "STATEFP"]].rename(
    columns={"STATEFP": "dominant_state_fips"}
)
print("\nDominant state per parent BA:")
for _, row in dominant_state.sort_values("BA_CODE").iterrows():
    print(f"  {row['BA_CODE']:<12} → state {row['dominant_state_fips']}")

# Normalise weights to sum to 1.0 per BA
ba_divs = ba_divs[ba_divs["div_num"].notna()].copy()
ba_divs["div_num"] = ba_divs["div_num"].astype(int)
totals = ba_divs.groupby("BA_CODE")["population"].transform("sum")
ba_divs["pop_weight"] = ba_divs["population"] / totals.clip(lower=1)
ba_divs = ba_divs.drop(columns="population").rename(columns={"BA_CODE": "entity"})

# ── 6. Sub-region manual state mapping ───────────────────────────────────
# For each sub-region, we know the dominant state from geography/utility knowledge
# state_fips → climate divisions within that state are used (equal pop-weighted)
SUBREGION_STATE_FIPS = {
    # CAISO sub-regions — all California (06)
    "CISO-PGAE": "06", "CISO-SCE": "06", "CISO-SDGE": "06", "CISO-VEA": "06",
    # ERCOT sub-regions — all Texas (48)
    "ERCO-COAS": "48", "ERCO-EAST": "48", "ERCO-FWES": "48",
    "ERCO-NCEN": "48", "ERCO-NRTH": "48", "ERCO-SCEN": "48",
    "ERCO-SOUT": "48", "ERCO-WEST": "48",
    # NYISO zones — all New York (36)
    "NYIS-ZONA": "36", "NYIS-ZONB": "36", "NYIS-ZONC": "36", "NYIS-ZOND": "36",
    "NYIS-ZONE": "36", "NYIS-ZONF": "36", "NYIS-ZONG": "36", "NYIS-ZONH": "36",
    "NYIS-ZONI": "36", "NYIS-ZONJ": "36", "NYIS-ZONK": "36",
    # ISO-NE zones — map to individual states
    "ISNE-4001": "23",  # Maine
    "ISNE-4002": "33",  # New Hampshire
    "ISNE-4003": "50",  # Vermont
    "ISNE-4004": "09",  # Connecticut
    "ISNE-4005": "44",  # Rhode Island
    "ISNE-4006": "25",  # Massachusetts (SE)
    "ISNE-4007": "25",  # Massachusetts (W/C)
    "ISNE-4008": "25",  # Massachusetts (NE)
    # MISO zones — best-match dominant state by zone geography
    "MISO-0001": "17",  # Illinois
    "MISO-0004": "27",  # Minnesota
    "MISO-0006": "26",  # Michigan
    "MISO-0027": "22",  # Louisiana
    "MISO-0035": "28",  # Mississippi
    "MISO-8910": "29",  # Missouri
    # PJM sub-regions — dominant state by utility territory
    "PJM-AE"  : "34",  # New Jersey (Atlantic City Electric)
    "PJM-AEP" : "39",  # Ohio (AEP largest load center)
    "PJM-AP"  : "42",  # Pennsylvania (Allegheny Power)
    "PJM-ATSI": "39",  # Ohio (American Transmission Systems)
    "PJM-BC"  : "24",  # Maryland (BGE)
    "PJM-CE"  : "39",  # Ohio (Duke Energy Ohio / Cincinnati)
    "PJM-DAY" : "39",  # Ohio (Dayton Power)
    "PJM-DEOK": "39",  # Ohio (Duke Energy Ohio)
    "PJM-DOM" : "51",  # Virginia (Dominion)
    "PJM-DPL" : "10",  # Delaware (Delmarva Power)
    "PJM-DUQ" : "42",  # Pennsylvania (Duquesne Light)
    "PJM-EKPC": "21",  # Kentucky (East KY Power)
    "PJM-JC"  : "34",  # New Jersey (Jersey Central Power)
    "PJM-ME"  : "42",  # Pennsylvania (Met-Ed)
    "PJM-PE"  : "42",  # Pennsylvania (Penn Power)
    "PJM-PEP" : "42",  # Pennsylvania (PPL)
    "PJM-PL"  : "42",  # Pennsylvania (PPL Electric)
    "PJM-PN"  : "42",  # Pennsylvania (Penn Power)
    "PJM-PS"  : "34",  # New Jersey (PSEG)
    # SPP sub-regions — dominant state by utility territory
    "SWPP-CSWS": "40",  # Oklahoma (Central & South West)
    "SWPP-EDE" : "29",  # Missouri (Empire District)
    "SWPP-GRDA": "40",  # Oklahoma (Grand River Dam)
    "SWPP-INDN": "40",  # Oklahoma (Indian Electric)
    "SWPP-KACY": "29",  # Missouri (Kansas City Power)
    "SWPP-KCPL": "29",  # Missouri (KCPL)
    "SWPP-LES" : "31",  # Nebraska (Lincoln Electric)
    "SWPP-MPS" : "29",  # Missouri (Missouri Public Service)
    "SWPP-NPPD": "31",  # Nebraska (NPPD)
    "SWPP-OKGE": "40",  # Oklahoma (OG&E)
    "SWPP-OPPD": "31",  # Nebraska (OPPD)
    "SWPP-SECI": "40",  # Oklahoma (Western Farmers)
    "SWPP-SPRM": "29",  # Missouri (City Utilities Springfield)
    "SWPP-SPS" : "48",  # Texas (Southwestern Public Service)
    "SWPP-WAUE": "38",  # North Dakota (WAPA Upper Missouri)
    "SWPP-WFEC": "40",  # Oklahoma (Western Farmers)
    "SWPP-WR"  : "20",  # Kansas (Westar/Evergy)
}

# For each sub-region: use all climate divisions in the dominant state,
# weighted by county population
state_divs = (
    county_gdf.groupby(["STATEFP", "state_fips", "div_num"])["population"]
    .sum()
    .reset_index()
    .dropna(subset=["div_num"])
)
state_divs["div_num"] = state_divs["div_num"].astype(int)

sub_rows = []
for entity, st_fips in SUBREGION_STATE_FIPS.items():
    divs = state_divs[state_divs["STATEFP"] == st_fips][["state_fips", "div_num", "population"]].copy()
    if divs.empty:
        print(f"  WARNING: no climate divisions found for {entity} (state {st_fips})")
        continue
    total = divs["population"].sum()
    divs["pop_weight"] = divs["population"] / max(total, 1)
    divs["entity"] = entity
    sub_rows.append(divs[["entity", "state_fips", "div_num", "pop_weight"]])

sub_df = pd.concat(sub_rows, ignore_index=True)

# ── 7. Combine and save ───────────────────────────────────────────────────
combined = pd.concat([ba_divs, sub_df], ignore_index=True)
combined = combined[combined["pop_weight"] > 0].copy()
out_path = OUT_DIR / "entity_climdiv_weights.parquet"
combined.to_parquet(out_path, index=False)
print(f"\nSaved {len(combined):,} rows → {out_path.name}")
print(f"Entities covered: {combined['entity'].nunique()}")
print("\nSample rows:")
print(combined[combined["entity"] == "CISO"].head())
