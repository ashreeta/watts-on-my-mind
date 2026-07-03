"""
Regenerate fig_f1.svg with per-panel (non-shared) y-axes.
Shared y-axis makes Germany dominate; this fixes readability.
Uses hardcoded data from notebook cell 18 output.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

OUT_DIR = "/Users/ashreeta/Downloads/Articles/articles/curtailment/figs"

PLOT_YEARS = list(range(2020, 2026))

PROD = {
    "CAISO":     {2020: 46928,  2021: 54522,  2022: 59197,  2023: 62077,  2024: 72988,  2025: 74387},
    "ERCOT":     {2020: 64000,  2021: 68000,  2022: 88000,  2023: 107000, 2024: 131000, 2025: 183000},
    "Germany":   {2020: 175751, 2021: 159806, 2022: 181461, 2023: 198071, 2024: 201376, 2025: 206746},
    "Australia": {2020: 22000,  2021: 28000,  2022: 37000,  2023: 49000,  2024: 58000,  2025: 71000},
}
CURT = {
    "CAISO":     {2020: 1587,  2021: 1505,  2022: 2449,  2023: 2660,  2024: 3423,  2025: 6507},
    "ERCOT":     {2020: 4500,  2021: 6300,  2022: 7700,  2023: 6300,  2024: 8200,  2025: 9800},
    "Germany":   {2020: 6745,  2021: 4764,  2022: 8000,  2023: 10400, 2024: 9335,  2025: 7300},
    "Australia": {2020: 800,   2021: 1200,  2022: 1700,  2023: 2200,  2024: 3100,  2025: 6700},
}
LABELS = {
    "CAISO":     "CAISO",
    "ERCOT":     "ERCOT ‡",
    "Germany":   "Germany ‡",
    "Australia": "Aus ‡",
}
COLORS = {
    "CAISO":     "#1f78b4",
    "ERCOT":     "#e31a1c",
    "Germany":   "#6a3d9a",
    "Australia": "#ff7f00",
}

REGIONS = ["CAISO", "ERCOT", "Germany", "Australia"]

# Compute shared y-axis upper limit across all regions
max_total = max(
    PROD[r][yr] + CURT[r].get(yr, 0)
    for r in REGIONS for yr in PLOT_YEARS if PROD[r].get(yr)
)
Y_MAX = max_total * 1.08  # 8% headroom

fig = make_subplots(
    rows=1, cols=4,
    subplot_titles=[LABELS[r] for r in REGIONS],
    horizontal_spacing=0.07,
    shared_yaxes=False,
)

for col, region in enumerate(REGIONS, start=1):
    yrs  = [yr for yr in PLOT_YEARS if PROD[region].get(yr) and CURT[region].get(yr) is not None]
    prod = [PROD[region][yr] for yr in yrs]
    curt = [CURT[region][yr] for yr in yrs]
    color = COLORS[region]

    fig.add_trace(go.Bar(
        x=yrs, y=prod,
        name="Delivered" if col == 1 else None,
        showlegend=(col == 1), legendgroup="deliv",
        marker_color=color, opacity=0.22,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh delivered<extra></extra>",
    ), row=1, col=col)

    fig.add_trace(go.Bar(
        x=yrs, y=curt,
        name="Curtailed" if col == 1 else None,
        showlegend=(col == 1), legendgroup="curt",
        marker_color=color, opacity=0.88,
        hovertemplate=f"<b>{region}</b> %{{x}}: %{{y:,.0f}} GWh curtailed<extra></extra>",
    ), row=1, col=col)

fig.update_layout(
    barmode="stack",
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18),
    height=380, template="plotly_white", margin=dict(t=30, b=70, l=65, r=20),
)
fig.update_xaxes(dtick=1, tickangle=45)
# Shared y-axis upper limit; ticks only on leftmost panel
for col_idx in range(1, 5):
    axis_key = f"yaxis{'' if col_idx == 1 else col_idx}"
    show_ticks = col_idx == 1
    fig.update_layout(**{axis_key: dict(
        tickformat=",.0f",
        range=[0, Y_MAX],
        showticklabels=show_ticks,
        showgrid=show_ticks,
    )})
fig.update_yaxes(title_text="GWh", col=1)

out_path = f"{OUT_DIR}/fig_f1.svg"
fig.write_image(out_path, format="svg", width=1100, height=420)
print(f"✓ {out_path}")
