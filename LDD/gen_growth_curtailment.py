"""
Generate fig_growth.svg — Growth in Curtailment vs. Wind+Solar Generation (% change from 2020).
Standalone script: all data hardcoded from notebook outputs.
Title/subtitle are in the QMD; this figure exports only the chart body + footnotes.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

OUT_DIR = "/Users/ashreeta/Downloads/Articles/articles/curtailment/figs"
os.makedirs(OUT_DIR, exist_ok=True)

PLOT_YEARS = list(range(2020, 2026))

# ── Data (CURT must match export_curtailment_figs.py's *_curt_ann dicts) ─────

PROD = {
    "CAISO":     {2020: 46928,  2021: 54522,  2022: 59197,  2023: 62077,  2024: 72988,  2025: 74387},
    "ERCOT":     {2020: 64000,  2021: 68000,  2022: 88000,  2023: 107000, 2024: 131000, 2025: 183000},
    "Germany":   {2020: 175751, 2021: 159806, 2022: 181461, 2023: 198071, 2024: 201376, 2025: 206746},
    "Australia": {2020: 22000,  2021: 28000,  2022: 37000,  2023: 49000,  2024: 58000,  2025: 71000},
}

CURT = {
    "CAISO":     {2020: 1588,  2021: 1505,  2022: 2449,  2023: 2660,  2024: 3423,  2025: 3766},
    "ERCOT":     {2020: 4500,  2021: 6300,  2022: 7700,  2023: 6300,  2024: 8200,  2025: 9800},
    "Germany":   {2020: 6745,  2021: 4764,  2022: 8000,  2023: 10400, 2024: 9335,  2025: 9380},
    "Australia": {2020: 800,   2021: 1200,  2022: 1700,  2023: 2200,  2024: 4300,  2025: 7200},
}

LABELS = {
    "CAISO":     "CAISO (California)",
    "ERCOT":     "ERCOT (Texas) †",      # † footnote for 2023 dip
    "Germany":   "Germany ‡",             # ‡ footnote for reporting change
    "Australia": "Australia (NEM)",
}

COLORS = {
    "CAISO":     "#1f78b4",
    "ERCOT":     "#e31a1c",
    "Germany":   "#6a3d9a",
    "Australia": "#ff7f00",
}

REGIONS = ["CAISO", "ERCOT", "Germany", "Australia"]

# ── Build figure ──────────────────────────────────────────────────────────────

fig = make_subplots(
    rows=1, cols=4,
    subplot_titles=[LABELS[r] for r in REGIONS],
    horizontal_spacing=0.07,
)

for col, region in enumerate(REGIONS, start=1):
    first    = (col == 1)
    base_yr  = 2020
    color    = COLORS[region]

    yrs = [yr for yr in PLOT_YEARS
           if CURT[region].get(yr) is not None and PROD[region].get(yr) is not None]
    if base_yr not in yrs:
        continue

    base_curt = CURT[region][base_yr]
    base_prod = PROD[region][base_yr]
    curt_pct  = [(CURT[region][yr] / base_curt - 1) * 100 for yr in yrs]
    prod_pct  = [(PROD[region][yr] / base_prod - 1) * 100 for yr in yrs]

    fig.add_trace(go.Scatter(
        x=yrs, y=curt_pct,
        name="Curtailment",
        legendgroup="curt", showlegend=first,
        mode="lines+markers",
        line=dict(color=color, width=2.5),
        marker=dict(size=7, color=color, line=dict(color="white", width=1.5)),
        hovertemplate=f"<b>{region}</b> %{{x}} curtailment: %{{y:+.0f}}% vs 2020<extra></extra>",
    ), row=1, col=col)

    fig.add_trace(go.Scatter(
        x=yrs, y=prod_pct,
        name="Wind + Solar generation",
        legendgroup="prod", showlegend=first,
        mode="lines+markers",
        line=dict(color=color, width=2.5, dash="dash"),
        marker=dict(size=7, color=color, symbol="diamond",
                    line=dict(color="white", width=1.5)),
        hovertemplate=f"<b>{region}</b> %{{x}} generation: %{{y:+.0f}}% vs 2020<extra></extra>",
    ), row=1, col=col)

    fig.add_hline(y=0, line=dict(color="#bbb", width=1, dash="dot"),
                  row=1, col=col)

fig.update_xaxes(dtick=1, tickangle=45, range=[2019.5, 2025.5])
fig.update_yaxes(ticksuffix="%")
fig.update_yaxes(title_text="% change from 2020", col=1)

fig.update_layout(
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.14, font=dict(size=18)),
    height=420, template="plotly_white",
    margin=dict(t=40, b=75, l=65, r=20),
)

out_path = f"{OUT_DIR}/fig_growth.svg"
fig.write_image(out_path, format="svg", width=1100, height=420)
print(f"✓ {out_path}")
