"""
Download NOAA nClimDiv monthly HDD and CDD by climate division.

Output: data/nclimdiv_hdd_monthly.parquet
        data/nclimdiv_cdd_monthly.parquet

Columns: state_fips (str), div_num (int), year (int), month (int), value (float)
"""

import io
import requests
import pandas as pd
from pathlib import Path

BASE_URL = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"
HDD_FILE = "climdiv-hddcdv-v1.0.0-20260506"
CDD_FILE = "climdiv-cddcdv-v1.0.0-20260506"

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def parse_climdiv(raw_text: str, start_year: int = 2015, end_year: int = 2024) -> pd.DataFrame:
    """
    nClimDiv format: each line is
      stFIPS(2) divNum(2) elemCode(2) year(4)  [12 monthly values]
    Monthly values are space-separated floats; -9.99 or -99.90 = missing.
    """
    rows = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        record_id = line[:10]
        state_fips = record_id[0:2]
        div_num    = int(record_id[2:4])
        # elem_code  = record_id[4:6]  # not needed — we know from the file
        year       = int(record_id[6:10])
        if year < start_year or year > end_year:
            continue
        values = line[10:].split()
        if len(values) < 12:
            continue
        for month_idx, v in enumerate(values[:12], start=1):
            val = float(v)
            if val < -9.0:   # -9.99 / -99.90 = missing
                val = float("nan")
            rows.append((state_fips, div_num, year, month_idx, val))
    return pd.DataFrame(rows, columns=["state_fips", "div_num", "year", "month", "value"])


def download_and_save(url: str, out_path: Path, label: str) -> pd.DataFrame:
    print(f"Downloading {label} from {url} ...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    df = parse_climdiv(r.text)
    df.to_parquet(out_path, index=False)
    print(f"  {len(df):,} rows → {out_path.name}")
    return df


if __name__ == "__main__":
    download_and_save(BASE_URL + HDD_FILE, OUT_DIR / "nclimdiv_hdd_monthly.parquet", "HDD")
    download_and_save(BASE_URL + CDD_FILE, OUT_DIR / "nclimdiv_cdd_monthly.parquet", "CDD")
    print("Done.")
