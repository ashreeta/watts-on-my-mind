"""
Export curtailment article figures as SVG files.
Runs required notebook cells in dependency order and writes SVGs to
articles/curtailment/figs/.
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import glob
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUT_DIR = "/Users/ashreeta/Downloads/Articles/articles/curtailment/figs"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Cell 1: data loading ──────────────────────────────────────────────────────

FUEL_DIR = "/Users/ashreeta/Downloads/Articles/LDD/CAISO_fuel_mix"
dfs = [pd.read_parquet(f) for f in sorted(glob.glob(FUEL_DIR + "/caiso_fuel_mix_*.parquet"))]
raw = pd.concat(dfs, ignore_index=True)
raw["local_dt"] = pd.to_datetime(raw["Interval Start"], utc=True).dt.tz_convert("America/Los_Angeles")
raw["year"]  = raw["local_dt"].dt.year
raw["month"] = raw["local_dt"].dt.month
raw["hour"]  = raw["local_dt"].dt.hour
raw["bat_discharge"] = raw["Batteries"].clip(lower=0)
raw["bat_charge"]    = raw["Batteries"].clip(upper=0)
raw = raw[raw["year"].between(2018, 2025)].copy()

CURT_DIR = "/Users/ashreeta/Downloads/Articles/LDD/productionandcurtailmentsdata"
curt_dfs = [pd.ExcelFile(f).parse("Curtailments")
            for f in sorted(glob.glob(CURT_DIR + "/*.xlsx"))]
curt_all = pd.concat(curt_dfs, ignore_index=True)
curt_all["Date"]  = pd.to_datetime(curt_all["Date"])
# Some source files overlap in date coverage (e.g. the 2025 file is superseded
# by a later full-year file); dedupe on the natural key to avoid double-counting.
curt_all = curt_all.drop_duplicates(subset=["Date", "Hour", "Interval", "Reason"])
curt_all["year"]  = curt_all["Date"].dt.year
curt_all["month"] = curt_all["Date"].dt.month
curt_all["hr"]    = (curt_all["Hour"].astype(int) - 1) % 24

ERCOT_CURT_DIR = "/Users/ashreeta/Downloads/Articles/LDD/ERCOT_curtailment"
ercot_curt = pd.concat(
    [pd.read_parquet(f) for f in sorted(glob.glob(ERCOT_CURT_DIR + "/sced_2*.parquet"))],
    ignore_index=True)
ercot_curt["data_date"] = pd.to_datetime(ercot_curt["data_date"].astype(str))
ercot_curt["year"]  = ercot_curt["data_date"].dt.year
ercot_curt["month"] = ercot_curt["data_date"].dt.month
ercot_curt["avg_curtailment_mw"] = ercot_curt["curtailment_sum_mw"] / ercot_curt["n_intervals"]
ercot_solar = ercot_curt[ercot_curt["fuel_type"] == "PVGR"].copy()
ercot_wind  = ercot_curt[ercot_curt["fuel_type"] == "WIND"].copy()

COLORS = {
    2018: "#313695", 2019: "#4575b4", 2020: "#74add1", 2021: "#abd9e9",
    2022: "#fdae61", 2023: "#f46d43", 2024: "#d73027", 2025: "#a50026",
}
YEARS     = sorted(raw["year"].unique())
ALL_YEARS = list(range(2018, 2026))

print("Data loaded. CAISO curtailment years:", sorted(curt_all["year"].unique()))

# ── Cell 7: SEASON_MAP ────────────────────────────────────────────────────────

SEASON_MAP = {1:"Winter",2:"Winter",3:"Spring",4:"Spring",5:"Spring",
              6:"Summer",7:"Summer",8:"Summer",9:"Fall",10:"Fall",11:"Fall",12:"Winter"}

# ── Cell 5: Chart D — CAISO Local vs System curtailment ──────────────────────

curt_by_reason = (curt_all
                  .assign(gwh_solar = lambda x: x["Solar Curtailment"] * (5/60) / 1000,
                          gwh_wind  = lambda x: x["Wind Curtailment"]  * (5/60) / 1000,
                          gwh_total = lambda x: (x["Solar Curtailment"] + x["Wind Curtailment"])
                                                * (5/60) / 1000)
                  .groupby(["year", "Reason"])[["gwh_solar", "gwh_wind", "gwh_total"]]
                  .sum()
                  .reset_index())

REASON_COLORS = {"System": "#4575b4", "Local": "#d73027"}
plot_years = sorted(curt_by_reason["year"].unique())

fig_d = go.Figure()
for reason in ["System", "Local"]:
    sub = (curt_by_reason[curt_by_reason["Reason"] == reason]
           .set_index("year"))
    y_vals = [sub.loc[yr, "gwh_total"] if yr in sub.index else 0 for yr in plot_years]
    fig_d.add_trace(go.Bar(
        x=plot_years, y=y_vals,
        name=reason,
        width=0.4,
        marker_color=REASON_COLORS.get(reason, "#aaa"),
        hovertemplate=f"<b>{reason}</b> %{{x}}: %{{y:,.0f}} GWh<extra></extra>",
    ))

fig_d.update_layout(
    barmode="stack",
    xaxis=dict(title=None, dtick=1, tickfont=dict(size=19)),
    yaxis=dict(title="Annual Curtailment<br>(GWh)", tickformat=",.0f", tickfont=dict(size=19),
               title_font=dict(size=18)),
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18, font=dict(size=20)),
    height=380, template="plotly_white",
    margin=dict(t=20, b=70, l=70, r=20),
)

fig_d.write_image(f"{OUT_DIR}/chart_d.svg", format="svg", width=480, height=280)
print("✓ chart_d.svg")

# ── Cell 9: Chart E — 4-region annual curtailment vs battery capacity ─────────

PLOT_YEARS = list(range(2020, 2026))

caiso_curt_ann = (
    curt_all
    .assign(gwh=lambda x: (x["Solar Curtailment"].fillna(0) + x["Wind Curtailment"].fillna(0))
                          * (5/60) / 1000)
    .groupby("year")["gwh"].sum()
    .reindex(PLOT_YEARS, fill_value=0).to_dict()
)

ercot_curt_ann = {2020: 4500, 2021: 6300, 2022: 7700, 2023: 6300, 2024: 8200, 2025: 9800}

germany_curt_ann = {2020: 6745, 2021: 4764, 2022: 8000, 2023: 10400, 2024: 9335, 2025: 9380}

australia_curt_ann = {2020: 800, 2021: 1200, 2022: 1700, 2023: 2200, 2024: 4300, 2025: 7200}

_df860 = pd.read_excel(
    "/Users/ashreeta/Downloads/Articles/LDD/EIA930_raw/april_generator2026.xlsx",
    sheet_name="Operating", header=2)
_df860["mwh"]     = pd.to_numeric(_df860["Nameplate Energy Capacity (MWh)"], errors="coerce")
_df860["op_year"] = pd.to_numeric(_df860["Operating Year"],                  errors="coerce")
_bat = _df860[_df860["Technology"] == "Batteries"].dropna(subset=["mwh", "op_year"])

def _bat_gwh(ba):
    sub = _bat[_bat["Balancing Authority Code"] == ba]
    ann = sub.groupby("op_year")["mwh"].sum()
    return {yr: ann[ann.index <= yr].sum() / 1000 for yr in PLOT_YEARS}

REGION_CFG = {
    "CAISO": dict(
        label="CAISO (California)", curt=caiso_curt_ann, bat=_bat_gwh("CISO"),
        color="#1f78b4", approx=False),
    "ERCOT": dict(
        label="ERCOT (Texas)", curt=ercot_curt_ann, bat=_bat_gwh("ERCO"),
        color="#e31a1c", approx=False),
    "Germany": dict(
        label="Germany ‡ (Redispatch 2.0)", curt=germany_curt_ann,
        bat={2020:0.7, 2021:0.7, 2022:1.2, 2023:1.5, 2024:1.9, 2025:3.5},
        color="#6a3d9a", approx=True),
    "Australia": dict(
        label="Australia ‡ (NEM)", curt=australia_curt_ann,
        bat={2020:0.7, 2021:1.0, 2022:2.2, 2023:3.7, 2024:7.0, 2025:15.0},
        color="#ff7f00", approx=True),
}

_max_curt = max(max(cfg["curt"].values()) for cfg in REGION_CFG.values())
_max_bat  = max(max(cfg["bat"].values())  for cfg in REGION_CFG.values())
_curt_ymax = _max_curt * 1.15
_bat_ymax  = _max_bat  * 1.15

fig_a = make_subplots(
    rows=1, cols=4,
    subplot_titles=[cfg["label"] for cfg in REGION_CFG.values()],
    specs=[[{"secondary_y": True}] * 4],
    horizontal_spacing=0.08,
)
for col, (region, cfg) in enumerate(REGION_CFG.items(), start=1):
    first   = (col == 1)
    yrs     = [yr for yr in PLOT_YEARS if cfg["curt"].get(yr) is not None]
    curt_v  = [cfg["curt"][yr] for yr in yrs]
    bat_v   = [cfg["bat"].get(yr) or 0 for yr in yrs]
    opacity = 0.40 if cfg["approx"] else 0.82

    fig_a.add_trace(go.Bar(
        x=yrs, y=curt_v, name="Curtailment (GWh/yr)",
        marker_color=cfg["color"], opacity=opacity,
        legendgroup="curt", showlegend=first,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh curtailed<extra></extra>",
    ), row=1, col=col, secondary_y=False)
    fig_a.add_trace(go.Scatter(
        x=yrs, y=bat_v, name="Battery capacity (GWh, cumulative)",
        mode="lines+markers", line=dict(color="#111111", width=2),
        marker=dict(size=6, color="#111111"),
        legendgroup="bat", showlegend=first,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:.2f}} GWh installed<extra></extra>",
    ), row=1, col=col, secondary_y=True)

fig_a.update_xaxes(dtick=1, tickangle=45)
fig_a.update_layout(
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18, font=dict(size=17)),
    height=400, template="plotly_white", margin=dict(t=20, b=80, l=60, r=40),
    yaxis =dict(range=[0, _curt_ymax], title_text="Curtailment (GWh/yr)", tickformat=",.0f"),
    yaxis3=dict(range=[0, _curt_ymax], tickformat=",.0f", showticklabels=False),
    yaxis5=dict(range=[0, _curt_ymax], tickformat=",.0f", showticklabels=False),
    yaxis7=dict(range=[0, _curt_ymax], tickformat=",.0f", showticklabels=False),
    yaxis2=dict(range=[0, _bat_ymax],  tickformat=".1f", showgrid=False, showticklabels=False),
    yaxis4=dict(range=[0, _bat_ymax],  tickformat=".1f", showgrid=False, showticklabels=False),
    yaxis6=dict(range=[0, _bat_ymax],  tickformat=".1f", showgrid=False, showticklabels=False),
    yaxis8=dict(range=[0, _bat_ymax],  title_text="Battery (GWh)", tickformat=".1f", showgrid=False),
)

fig_a.write_image(f"{OUT_DIR}/chart_e.svg", format="svg", width=1100, height=440)
print("✓ chart_e.svg")

# ── Cells 14+15: fig_dis2 — curtailment + charge + discharge ──────────────────

caiso_discharge_ann = (
    raw[raw["year"].between(2020, 2025)]
    .groupby("year")
    .apply(lambda g: (g["bat_discharge"] * (5/60) / 1000).sum())
    .reindex(PLOT_YEARS, fill_value=0).to_dict()
)

ESR_DIR = "/Users/ashreeta/Downloads/Articles/LDD/ERCOT_ESR"
esr_all = pd.concat(
    [pd.read_parquet(f) for f in sorted(glob.glob(ESR_DIR + "/*.parquet"))],
    ignore_index=True)
esr_all["year"] = pd.to_datetime(esr_all["date"].astype(str)).dt.year
ercot_discharge_ann = (
    esr_all[esr_all["year"].between(2020, 2025)]
    .groupby("year")["discharge_mw"]
    .sum().div(1000)
    .reindex(PLOT_YEARS, fill_value=None).to_dict()
)

caiso_charge_ann = (
    raw[raw["year"].between(2020, 2025)]
    .assign(bat_charge=lambda x: x["Batteries"].clip(upper=0).abs())
    .groupby("year")
    .apply(lambda g: (g["bat_charge"] * (5/60) / 1000).sum())
    .reindex(PLOT_YEARS, fill_value=0).to_dict()
)

ercot_charge_ann = (
    esr_all[esr_all["year"].between(2020, 2025)]
    .groupby("year")["charge_mw"]
    .sum().div(1000)
    .reindex(PLOT_YEARS, fill_value=None).to_dict()
)

DISV2_CFG = {
    "CAISO": dict(
        label="CAISO (California)", color="#1f78b4",
        curt=caiso_curt_ann, discharge=caiso_discharge_ann, charge=caiso_charge_ann,
    ),
    "ERCOT": dict(
        label="ERCOT (Texas)", color="#e31a1c",
        curt=ercot_curt_ann, discharge=ercot_discharge_ann, charge=ercot_charge_ann,
    ),
}

fig_dis2 = make_subplots(
    rows=1, cols=2,
    subplot_titles=[cfg["label"] for cfg in DISV2_CFG.values()],
    shared_yaxes=True,
    horizontal_spacing=0.06,
)

for col, (region, cfg) in enumerate(DISV2_CFG.items(), start=1):
    first = (col == 1)
    yrs    = [yr for yr in PLOT_YEARS if cfg["curt"].get(yr) is not None]
    curt_v = [cfg["curt"].get(yr, 0) for yr in yrs]
    dis_yrs = [yr for yr in PLOT_YEARS if cfg["discharge"].get(yr)]
    dis_v   = [cfg["discharge"][yr] for yr in dis_yrs]
    chg_yrs = [yr for yr in PLOT_YEARS if cfg["charge"].get(yr)]
    chg_v   = [cfg["charge"][yr] for yr in chg_yrs]

    fig_dis2.add_trace(go.Bar(
        x=yrs, y=curt_v, name="Curtailment (GWh)",
        marker_color=cfg["color"], opacity=0.75,
        legendgroup="curt", showlegend=first,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh curtailed<extra></extra>",
    ), row=1, col=col)

    fig_dis2.add_trace(go.Scatter(
        x=dis_yrs, y=dis_v, name="Battery discharge (GWh)",
        mode="lines+markers", line=dict(color="#111", width=2.5),
        marker=dict(size=8, color="#111", line=dict(color="white", width=1.5)),
        legendgroup="dis", showlegend=first,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh discharged<extra></extra>",
    ), row=1, col=col)

    fig_dis2.add_trace(go.Scatter(
        x=chg_yrs, y=chg_v, name="Battery charge (GWh)",
        mode="lines+markers", line=dict(color="#888", width=2, dash="dash"),
        marker=dict(size=7, color="#888", line=dict(color="white", width=1.5)),
        legendgroup="chg", showlegend=first,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh charged<extra></extra>",
    ), row=1, col=col)

fig_dis2.update_xaxes(dtick=1, tickangle=45)
fig_dis2.update_yaxes(title_text="GWh", tickformat=",.0f", col=1)
fig_dis2.update_layout(
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18),
    height=400, template="plotly_white",
    margin=dict(t=20, b=80, l=60, r=20),
)
fig_dis2.add_annotation(
    text="* 2022 CAISO battery charge understated: charging was classified as negative load in the Oasis fuel mix source.",
    xref="paper", yref="paper", x=0, y=-0.25,
    showarrow=False, font=dict(size=9, color="#555"), align="left",
)

fig_dis2.write_image(f"{OUT_DIR}/fig_dis2.svg", format="svg", width=900, height=460)
print("✓ fig_dis2.svg")

# ── Cells 17+18: fig_f1 (delivered vs curtailed) and fig_f2 (curtailment rate) ─

RENEW_COLS = ["Solar", "Wind", "Geothermal", "Biomass", "Biogas", "Small Hydro", "Large Hydro"]
caiso_renew = (
    raw[raw["year"].between(2020, 2025)]
    .assign(**{c: raw[c].clip(lower=0) for c in RENEW_COLS})
    .groupby("year")[RENEW_COLS].sum()
    .mul(5/60/1000)
)

try:
    import requests
    import urllib3
    urllib3.disable_warnings()
    _SMARD = "https://www.smard.de/app/chart_data"
    _DE_FILTERS = {"Offshore Wind": 1225, "Onshore Wind": 4067, "Solar PV": 4068}
    _YEAR_TS = {2020:1577833200000, 2021:1609455600000, 2022:1640991600000,
                2023:1672527600000, 2024:1704063600000, 2025:1735686000000}
    de_renew = {}
    for yr, ts in _YEAR_TS.items():
        de_renew[yr] = {}
        for label, fid in _DE_FILTERS.items():
            try:
                r = requests.get(f"{_SMARD}/{fid}/DE/{fid}_DE_year_{ts}.json",
                                 verify=False, timeout=10)
                de_renew[yr][label] = r.json()["series"][0][1]/1000 if r.ok and r.json().get("series") else None
            except Exception:
                de_renew[yr][label] = None
    de_renew_df = pd.DataFrame(de_renew).T
    de_renew_df["WindSolar"] = (de_renew_df.get("Onshore Wind", pd.Series()).fillna(0)
                                + de_renew_df.get("Offshore Wind", pd.Series()).fillna(0)
                                + de_renew_df.get("Solar PV", pd.Series()).fillna(0))
    _de_ok = de_renew_df["WindSolar"].sum() > 0
except Exception:
    de_renew_df = pd.DataFrame()
    _de_ok = False

print(f"Germany SMARD data {'loaded' if _de_ok else 'FAILED — Germany will be absent from fig_f1/f2'}")

ercot_renew_ann = {2020: 64_000, 2021: 68_000, 2022: 88_000,
                   2023: 107_000, 2024: 131_000, 2025: 183_000}
aus_renew_ann   = {2020: 22_000, 2021: 28_000, 2022: 37_000,
                   2023: 49_000,  2024: 58_000,  2025: 71_000}

def _de_windsolar(yr):
    if not _de_ok or yr not in de_renew_df.index:
        return None
    row = de_renew_df.loc[yr]
    val = (row.get("Onshore Wind") or 0) + (row.get("Offshore Wind") or 0) + (row.get("Solar PV") or 0)
    return val if val > 0 else None

PROD_CFG = {
    "CAISO": dict(
        label="CAISO", color="#1f78b4",
        prod={yr: (caiso_renew.loc[yr, "Solar"] + caiso_renew.loc[yr, "Wind"])
                  if yr in caiso_renew.index else None
              for yr in PLOT_YEARS},
        curt=caiso_curt_ann,
    ),
    "ERCOT": dict(label="ERCOT ‡", color="#e31a1c", prod=ercot_renew_ann, curt=ercot_curt_ann),
    "Germany": dict(
        label="Germany ‡", color="#6a3d9a",
        prod={yr: _de_windsolar(yr) for yr in PLOT_YEARS},
        curt=germany_curt_ann,
    ),
    "Australia": dict(label="Aus ‡", color="#ff7f00", prod=aus_renew_ann, curt=australia_curt_ann),
}

fig_f1 = make_subplots(
    rows=1, cols=4,
    subplot_titles=[cfg["label"] for cfg in PROD_CFG.values()],
    horizontal_spacing=0.07,
    shared_yaxes=True,
)
for col, (region, cfg) in enumerate(PROD_CFG.items(), start=1):
    yrs  = [yr for yr in PLOT_YEARS if cfg["prod"].get(yr) and cfg["curt"].get(yr) is not None]
    prod = [cfg["prod"][yr] for yr in yrs]
    curt = [cfg["curt"][yr] for yr in yrs]
    fig_f1.add_trace(go.Bar(
        x=yrs, y=prod,
        name="Delivered" if col == 1 else None,
        showlegend=(col == 1), legendgroup="deliv",
        marker_color=cfg["color"], opacity=0.22,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh delivered<extra></extra>",
    ), row=1, col=col)
    fig_f1.add_trace(go.Bar(
        x=yrs, y=curt,
        name="Curtailed" if col == 1 else None,
        showlegend=(col == 1), legendgroup="curt",
        marker_color=cfg["color"], opacity=0.88,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh curtailed<extra></extra>",
    ), row=1, col=col)

fig_f1.update_layout(
    barmode="stack",
    yaxis=dict(title="Annual Wind + Solar Generation (GWh)", tickformat=",.0f"),
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18),
    height=380, template="plotly_white", margin=dict(t=20, b=70, l=65, r=20),
)
fig_f1.update_xaxes(dtick=1, tickangle=45)

fig_f1.write_image(f"{OUT_DIR}/fig_f1.svg", format="svg", width=1100, height=420)
print("✓ fig_f1.svg")

fig_f1c = make_subplots(
    rows=1, cols=4,
    subplot_titles=[cfg["label"] for cfg in PROD_CFG.values()],
    horizontal_spacing=0.07,
    shared_yaxes=True,
)
for col, (region, cfg) in enumerate(PROD_CFG.items(), start=1):
    yrs  = [yr for yr in PLOT_YEARS if cfg["curt"].get(yr) is not None]
    curt = [cfg["curt"][yr] for yr in yrs]
    fig_f1c.add_trace(go.Bar(
        x=yrs, y=curt,
        showlegend=False,
        marker_color=cfg["color"],
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh curtailed<extra></extra>",
    ), row=1, col=col)

fig_f1c.update_layout(
    yaxis=dict(title="Annual Wind + Solar Curtailment (GWh)", tickformat=",.0f"),
    height=380, template="plotly_white", margin=dict(t=20, b=70, l=65, r=20),
)
fig_f1c.update_xaxes(dtick=1, tickangle=45)

fig_f1c.write_image(f"{OUT_DIR}/fig_f1c.svg", format="svg", width=1100, height=420)
print("✓ fig_f1c.svg")

fig_f2 = go.Figure()
for region, cfg in PROD_CFG.items():
    yrs   = [yr for yr in PLOT_YEARS if cfg["prod"].get(yr) and cfg["curt"].get(yr) is not None]
    rates = [cfg["curt"][yr] / (cfg["prod"][yr] + cfg["curt"][yr]) * 100 for yr in yrs]
    approx = region in ("ERCOT", "Germany", "Australia")
    fig_f2.add_trace(go.Scatter(
        x=yrs, y=rates, name=cfg["label"], mode="lines+markers",
        line=dict(color=cfg["color"], width=2.5, dash="dot" if approx else "solid"),
        marker=dict(size=8, color=cfg["color"], line=dict(color="white", width=1.5)),
        opacity=0.65 if approx else 1.0,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:.1f}}%<extra></extra>",
    ))
    if yrs:
        fig_f2.add_annotation(
            x=yrs[-1], y=rates[-1],
            text=f"  {region}  {rates[-1]:.1f}%",
            showarrow=False, xanchor="left", yanchor="middle",
            font=dict(size=10, color=cfg["color"]),
        )

fig_f2.update_layout(
    xaxis=dict(title="Year", dtick=1),
    yaxis=dict(title="Curtailment rate (%)", ticksuffix="%", rangemode="tozero"),
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18),
    height=360, template="plotly_white", margin=dict(t=20, b=70, l=70, r=160),
)

fig_f2.write_image(f"{OUT_DIR}/fig_f2.svg", format="svg", width=820, height=400)
print("✓ fig_f2.svg")

# ── Cell 21: CAISO+ERCOT 4×2 seasonal charging/curtailment/LMP ───────────────

raw24 = raw[raw["year"] == 2024].copy()
raw24["season"] = raw24["month"].map(SEASON_MAP)
bat_seas = (raw24.groupby(["season","hour"])["bat_charge"]
            .mean().abs().reset_index()
            .rename(columns={"bat_charge": "mean_charge_mw"}))
curt24 = curt_all[curt_all["year"] == 2024].copy()
curt24["season"] = curt24["month"].map(SEASON_MAP)
curt24["total_curt"] = (curt24["Solar Curtailment"].fillna(0) + curt24["Wind Curtailment"].fillna(0))
curt_seas = (curt24.groupby(["season","hr"])["total_curt"]
             .mean().reset_index()
             .rename(columns={"hr": "hour", "total_curt": "mean_curt_mw"}))

LMP_DIR = "/Users/ashreeta/Downloads/Articles/LDD/CAISO_LMP"
_lmp_ca = pd.concat(
    [pd.read_parquet(f) for f in sorted(glob.glob(LMP_DIR + "/*.parquet"))],
    ignore_index=True)
_lmp_ca["local_dt"] = pd.to_datetime(_lmp_ca["Interval Start"]).dt.tz_convert("America/Los_Angeles")
_lmp_ca["year"]   = _lmp_ca["local_dt"].dt.year
_lmp_ca["month"]  = _lmp_ca["local_dt"].dt.month
_lmp_ca["hour"]   = _lmp_ca["local_dt"].dt.hour
_lmp_ca["season"] = _lmp_ca["month"].map(SEASON_MAP)
lmp_ca_seas = (_lmp_ca[_lmp_ca["year"] == 2024]
               .groupby(["season","hour"])["LMP"].mean().reset_index())

esr_2024 = pd.concat(
    [pd.read_parquet(f) for f in sorted(glob.glob(ESR_DIR + "/esr_2024*.parquet"))],
    ignore_index=True)
esr_2024["hour"]   = esr_2024["hour_ending"] - 1
esr_2024["month"]  = pd.to_datetime(esr_2024["date"]).dt.month
esr_2024["season"] = esr_2024["month"].map(SEASON_MAP)
esr_seas = (esr_2024.groupby(["season","hour"])["charge_mw"]
            .mean().reset_index()
            .rename(columns={"charge_mw": "mean_charge_mw"}))

sced24 = ercot_curt[ercot_curt["year"] == 2024].copy()
sced24["season"] = sced24["month"].map(SEASON_MAP)
_OVERNIGHT = list(range(0, 6)) + list(range(21, 24))
sced24.loc[(sced24["fuel_type"] == "PVGR") & (sced24["hour"].isin(_OVERNIGHT)),
           "curtailment_sum_mw"] = 0
sced24["curt_mw"] = sced24["curtailment_sum_mw"] * (5 / 60)
daily_er = sced24.groupby(["data_date","season","hour"])["curt_mw"].sum().reset_index()
erc_curt_seas = (daily_er.groupby(["season","hour"])["curt_mw"]
                 .mean().reset_index()
                 .rename(columns={"curt_mw": "mean_curt_mw"}))

PRICE_DIR = "/Users/ashreeta/Downloads/Articles/LDD/ERCOT_prices"
_px_frames = []
for _year in [2024, 2025]:
    try:
        _xl = pd.ExcelFile(f"{PRICE_DIR}/DAMLZHBSPP_{_year}.xlsx")
        for _sheet in _xl.sheet_names:
            _df = _xl.parse(_sheet)
            _df = _df[_df["Settlement Point"] == "HB_NORTH"].copy()
            if _df.empty:
                continue
            _df["date"]   = pd.to_datetime(_df["Delivery Date"]).dt.date
            _df["hour"]   = _df["Hour Ending"].str.extract(r"(\d+)").astype(int) - 1
            _df["month"]  = pd.to_datetime(_df["Delivery Date"]).dt.month
            _df["season"] = _df["month"].map(SEASON_MAP)
            _px_frames.append(
                _df[["date","hour","season","Settlement Point Price"]]
                .rename(columns={"Settlement Point Price": "price"})
            )
    except FileNotFoundError:
        pass

_hub_px = pd.concat(_px_frames, ignore_index=True)
_hub_px["year"] = pd.to_datetime(_hub_px["date"].astype(str)).dt.year
_hub_px = _hub_px[_hub_px["year"] == 2024]
lmp_er_seas = (_hub_px.groupby(["season","hour"])["price"]
               .mean().reset_index()
               .rename(columns={"price": "lmp"}))

CA_P_TICKS = [-40, -20, 0, 20, 40, 60, 80, 100]
CA_D_TICKS = [-2000, -1000, 0, 1000, 2000, 3000, 4000, 5000]
CA_P_RANGE = [-50, 110]
CA_D_RANGE = [-2500, 5500]
ER_P_TICKS = [0, 20, 40, 60, 80, 100, 120, 140]
ER_D_TICKS = [0, 250, 500, 750, 1000, 1250, 1500, 1750]
ER_P_RANGE = [-10, 150]
ER_D_RANGE = [-125, 1875]

hours = np.arange(24)
cfg_list = [
    dict(bat=bat_seas,   bat_col="mean_charge_mw",
         curt=curt_seas, curt_col="mean_curt_mw",
         lmp=lmp_ca_seas, lmp_col="LMP",
         p_ticks=CA_P_TICKS, d_ticks=CA_D_TICKS,
         p_range=CA_P_RANGE, d_range=CA_D_RANGE),
    dict(bat=esr_seas,       bat_col="mean_charge_mw",
         curt=erc_curt_seas, curt_col="mean_curt_mw",
         lmp=lmp_er_seas,    lmp_col="lmp",
         p_ticks=ER_P_TICKS, d_ticks=ER_D_TICKS,
         p_range=ER_P_RANGE, d_range=ER_D_RANGE),
]

# Panels in reading order: (cfg_idx, season, row, col)
# Rows 1-2 = CAISO (2 seasons per row), rows 3-4 = ERCOT (2 seasons per row)
PANEL_ORDER = [
    (0, "Winter", 1, 1), (0, "Summer", 1, 2),
    (0, "Spring", 2, 1), (0, "Fall",   2, 2),
    (1, "Winter", 3, 1), (1, "Summer", 3, 2),
    (1, "Spring", 4, 1), (1, "Fall",   4, 2),
]

# Font sizes — at export_width=1000, display_font = export_font × (800/1000) ≈ 12px
TICK_FONT  = 15
TITLE_FONT = 16

fig_seasonal = make_subplots(
    rows=4, cols=2,
    subplot_titles=["Winter", "Summer", "Spring", "Fall",
                    "Winter", "Summer", "Spring", "Fall"],
    specs=[[{"secondary_y": True}, {"secondary_y": True}]] * 4,
    horizontal_spacing=0.10,
    vertical_spacing=0.09,
)

for cfg_idx, season, row_idx, col_idx in PANEL_ORDER:
    cfg   = cfg_list[cfg_idx]
    first = (row_idx == 1 and col_idx == 1)
    b  = (cfg["bat"][cfg["bat"]["season"] == season]
          .set_index("hour")[cfg["bat_col"]]
          .reindex(hours, fill_value=0.0))
    ct = (cfg["curt"][cfg["curt"]["season"] == season]
          .set_index("hour")[cfg["curt_col"]]
          .reindex(hours, fill_value=0.0))
    lp = (cfg["lmp"][cfg["lmp"]["season"] == season]
          .set_index("hour")[cfg["lmp_col"]]
          .reindex(hours))

    fig_seasonal.add_trace(go.Scatter(
        x=list(hours), y=list(lp), mode="lines",
        name="Mean LMP", legendgroup="lmp", showlegend=first,
        line=dict(color="#1e293b", width=3),
        hovertemplate="%{y:.1f} $/MWh<extra></extra>",
    ), row=row_idx, col=col_idx, secondary_y=False)

    fig_seasonal.add_trace(go.Bar(
        x=list(hours - 0.21), y=list(b), width=0.4,
        name="Battery charging", legendgroup="charge", showlegend=first,
        marker_color="#0891b2", opacity=0.85,
        hovertemplate="%{y:.0f} MW<extra></extra>",
    ), row=row_idx, col=col_idx, secondary_y=True)

    fig_seasonal.add_trace(go.Bar(
        x=list(hours + 0.21), y=list(ct), width=0.4,
        name="Curtailment", legendgroup="curt", showlegend=first,
        marker_color="#e11d48", opacity=0.85,
        hovertemplate="%{y:.0f} MW<extra></extra>",
    ), row=row_idx, col=col_idx, secondary_y=True)

    # LMP (primary, left): ticks on col 1, title on first row of each region block
    fig_seasonal.update_yaxes(
        range=cfg["p_range"], tickmode="array", tickvals=cfg["p_ticks"],
        tickformat="$d", tickfont=dict(color="#1e293b", size=TICK_FONT),
        showgrid=True, gridcolor="#e8e8e8",
        zeroline=True, zerolinecolor="#cccccc", zerolinewidth=1,
        showticklabels=(col_idx == 1),
        title_text="$/MWh" if (col_idx == 1 and row_idx in [1, 3]) else None,
        title_font=dict(color="#1e293b", size=TITLE_FONT),
        secondary_y=False, row=row_idx, col=col_idx,
    )
    # MW (secondary, right): ticks on col 2, title on first row of each region block
    fig_seasonal.update_yaxes(
        range=cfg["d_range"], tickmode="array", tickvals=cfg["d_ticks"],
        tickformat=",d", tickfont=dict(size=TICK_FONT),
        showgrid=False, zeroline=False,
        showticklabels=(col_idx == 2),
        title_text="MW" if (col_idx == 2 and row_idx in [1, 3]) else None,
        title_font=dict(size=TITLE_FONT),
        secondary_y=True, row=row_idx, col=col_idx,
    )

fig_seasonal.update_xaxes(
    tickvals=[0, 4, 8, 12, 16, 20],
    tickfont=dict(size=TICK_FONT),
    showgrid=False,
)
# x-axis title at the bottom of each region block
fig_seasonal.update_xaxes(title_text="Hour of day", title_font=dict(size=TITLE_FONT), row=2)
fig_seasonal.update_xaxes(title_text="Hour of day", title_font=dict(size=TITLE_FONT), row=4)
fig_seasonal.update_xaxes(title_text="", row=1)
fig_seasonal.update_xaxes(title_text="", row=3)

fig_seasonal.for_each_annotation(lambda a: a.update(font=dict(size=TITLE_FONT + 1)))

fig_seasonal.update_layout(
    height=1300,
    template="plotly_white",
    barmode="overlay",
    legend=dict(orientation="h", yanchor="top", y=-0.08,
                xanchor="center", x=0.5, font=dict(size=TICK_FONT)),
    margin=dict(l=95, r=90, t=40, b=130),
    annotations=list(fig_seasonal.layout.annotations) + [
        dict(text="CAISO (California)", x=-0.08, y=0.77, xref="paper", yref="paper",
             showarrow=False, textangle=-90, font=dict(size=TITLE_FONT, color="#333"),
             xanchor="center", yanchor="middle"),
        dict(text="ERCOT (Texas)", x=-0.08, y=0.23, xref="paper", yref="paper",
             showarrow=False, textangle=-90, font=dict(size=TITLE_FONT, color="#333"),
             xanchor="center", yanchor="middle"),
    ],
)

fig_seasonal.write_image(f"{OUT_DIR}/fig_seasonal.svg", format="svg", width=1000, height=1300)
print("✓ fig_seasonal.svg")

print("\nAll figures exported to", OUT_DIR)
