"""
Generate battery_energy_growth.svg — Figure 1b.
Same structure as gen_battery_capacity_growth.py but in GWh (energy)
instead of GW (power). Planned GWh estimated using each BA's operating
average duration (MWh/MW) applied to planned MW.
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import os

EIA860M_PATH = "/Users/ashreeta/Downloads/Articles/LDD/EIA930_raw/april_generator2026.xlsx"
OUT_SVG      = "/Users/ashreeta/Downloads/Articles/articles/caiso-ercot-storage/figs/battery_energy_growth.svg"

# ── Load operating sheet ──────────────────────────────────────────────────────
df860 = pd.read_excel(EIA860M_PATH, sheet_name="Operating", header=2)

def prep_operating(ba_code):
    b = df860[(df860["Balancing Authority Code"] == ba_code) &
              (df860["Technology"] == "Batteries")].copy()
    b["mwh"]     = pd.to_numeric(b["Nameplate Energy Capacity (MWh)"], errors="coerce")
    b["op_year"] = pd.to_numeric(b["Operating Year"],                  errors="coerce")
    return b.dropna(subset=["mwh", "op_year"])

bat_ca = prep_operating("CISO")
bat_tx = prep_operating("ERCO")

# Average duration (MWh/MW) per BA — used to estimate planned GWh
avg_dur_ca = bat_ca["mwh"].sum() / pd.to_numeric(bat_ca["Net Summer Capacity (MW)"], errors="coerce").sum()
avg_dur_tx = bat_tx["mwh"].sum() / pd.to_numeric(bat_tx["Net Summer Capacity (MW)"], errors="coerce").sum()
print(f"Avg duration — CAISO: {avg_dur_ca:.2f}h  ERCOT: {avg_dur_tx:.2f}h")

# ── Operating cumulative GWh (2010–2026) ─────────────────────────────────────
CA_GWH = (bat_ca[bat_ca["op_year"].between(2010, 2026)]
          .groupby("op_year")["mwh"].sum()
          .reindex(range(2010, 2027), fill_value=0).cumsum() / 1000)

TX_GWH = (bat_tx[bat_tx["op_year"].between(2010, 2026)]
          .groupby("op_year")["mwh"].sum()
          .reindex(range(2010, 2027), fill_value=0).cumsum() / 1000)

# ── Load planned sheet ────────────────────────────────────────────────────────
pl = pd.read_excel(EIA860M_PATH, sheet_name="Planned", header=2)
pl["status_code"] = pl["Status"].str.extract(r"^\(([^)]+)\)")
pl["cap_mw"]      = pd.to_numeric(pl["Net Summer Capacity (MW)"],  errors="coerce")
pl["plan_year"]   = pd.to_numeric(pl["Planned Operation Year"],    errors="coerce")

bat_pl     = pl[(pl["Technology"] == "Batteries") &
                (pl["status_code"].isin(["T", "TS", "U", "V"]))].copy()
bat_pl_all = pl[pl["Technology"] == "Batteries"].copy()

# ── Planned extension (GWh = planned MW × avg operating duration) ─────────────
def planned_extension_gwh(ba_code, growth_gwh, planned_df, avg_dur):
    annual_mw = (planned_df[planned_df["Balancing Authority Code"] == ba_code]
                 .groupby("plan_year")["cap_mw"].sum()
                 .reindex([2026, 2027, 2028], fill_value=0))
    base = growth_gwh.iloc[-1]
    xs, ys, cum = [2026], [base], base
    for yr in [2026, 2027, 2028]:
        cum += annual_mw.get(yr, 0) * avg_dur / 1000   # MW × h / 1000 → GWh
        xs.append(yr + 1)
        ys.append(cum)
    return xs, ys

ca_px,     ca_py     = planned_extension_gwh("CISO", CA_GWH, bat_pl,     avg_dur_ca)
tx_px,     tx_py     = planned_extension_gwh("ERCO", TX_GWH, bat_pl,     avg_dur_tx)
ca_px_all, ca_py_all = planned_extension_gwh("CISO", CA_GWH, bat_pl_all, avg_dur_ca)
tx_px_all, tx_py_all = planned_extension_gwh("ERCO", TX_GWH, bat_pl_all, avg_dur_tx)

# ── Palette (identical to Figure 1a) ─────────────────────────────────────────
_CA_CLR    = '#2166ac'
_TX_CLR    = '#d6604d'
_AX_BG     = '#ffffff'
_GRID_CLR  = '#e4e2da'
_TICK_CLR  = '#aaaaaa'
_TITLE_CLR = '#111111'
_LABEL_CLR = '#222222'
_NOTE_CLR  = '#999999'
_SPINE_CLR = '#e4e2da'

plt.rcParams.update({
    'svg.fonttype':    'none',
    'font.family':     'sans-serif',
    'font.sans-serif': ['Inter', 'Helvetica Neue', 'Arial', 'DejaVu Sans'],
    'axes.facecolor':  _AX_BG,
    'figure.facecolor':'#ffffff',
    'text.color':      _LABEL_CLR,
})

_CA_op = CA_GWH[CA_GWH.index >= 2018]
_TX_op = TX_GWH[TX_GWH.index >= 2018]

fig, ax = plt.subplots(figsize=(10, 5.8))
fig.patch.set_facecolor('#ffffff')
ax.set_facecolor(_AX_BG)

ax.yaxis.grid(True, color=_GRID_CLR, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)

# Operating lines
ax.plot(_CA_op.index, _CA_op.values,
        color=_CA_CLR, lw=3.5, solid_capstyle='round', zorder=3)
ax.plot(_TX_op.index, _TX_op.values,
        color=_TX_CLR, lw=3.5, solid_capstyle='round', zorder=3)

# Filtered planned lines (dashed)
ax.plot(ca_px, ca_py, color=_CA_CLR, lw=2.5, ls='--', dashes=(6, 3), zorder=3)
ax.plot(tx_px, tx_py, color=_TX_CLR, lw=2.5, ls='--', dashes=(6, 3), zorder=3)

# Full planned lines (dotted)
ax.plot(ca_px_all, ca_py_all, color=_CA_CLR, lw=2.0, ls=':', dashes=(1.5, 3), zorder=3, alpha=0.65)
ax.plot(tx_px_all, tx_py_all, color=_TX_CLR, lw=2.0, ls=':', dashes=(1.5, 3), zorder=3, alpha=0.65)

# Axis limits
_ymax = max(max(ca_py_all), max(tx_py_all)) * 1.18
ax.set_xlim(2017.7, 2031.8)
ax.set_ylim(0, _ymax)

# Vertical reference line
ax.axvline(2026.35, color=_GRID_CLR, lw=1.0, ls=':', zorder=1)
ax.text(2026.5, _ymax * 0.98, 'Planned ->',
        fontsize=13, color=_NOTE_CLR, va='top', ha='left', style='italic')

# Convergence label at 2026
_ca_end = CA_GWH[2026]
_tx_end = TX_GWH[2026]
_higher = max(_ca_end, _tx_end)
ax.text(2026.55, _higher + _ymax * 0.01,
        f'CA {_ca_end:.0f} / TX {_tx_end:.0f} GWh',
        color='#111111', fontsize=12, fontweight='bold', va='bottom', ha='left')

# End labels at 2029
_ca_dash_end = ca_py[-1]
_tx_dash_end = tx_py[-1]
_ca_dot_end  = ca_py_all[-1]
_tx_dot_end  = tx_py_all[-1]
_sp = _ymax * 0.04
_lx = 2029.15

ax.text(_lx, _ca_dash_end,        f'CA  {_ca_dash_end:.0f} GWh', color=_CA_CLR,
        fontsize=12, fontweight='bold', va='center', ha='left')
ax.text(_lx, _tx_dash_end + _sp,  f'TX  {_tx_dash_end:.0f} GWh', color=_TX_CLR,
        fontsize=12, fontweight='bold', va='center', ha='left')
ax.text(_lx, _ca_dot_end,         f'CA  {_ca_dot_end:.0f} GWh', color=_CA_CLR,
        fontsize=11, va='center', ha='left', alpha=0.7)
ax.text(_lx, _tx_dot_end,         f'{_tx_dot_end:.0f} GWh', color=_TX_CLR,
        fontsize=11, va='center', ha='left', alpha=0.7)

# Axes styling
ax.set_xticks(range(2018, 2030, 2))
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:.0f} GWh'))
ax.spines[['top', 'right']].set_visible(False)
ax.spines['left'].set_color(_SPINE_CLR)
ax.spines['bottom'].set_color(_SPINE_CLR)
ax.tick_params(axis='both', colors=_TICK_CLR, labelsize=13, length=0)
ax.tick_params(axis='x', length=3, color=_SPINE_CLR)

# Legend
_legend_els = [
    Line2D([0], [0], color=_CA_CLR, lw=3.5, label='California (CAISO)'),
    Line2D([0], [0], color=_TX_CLR, lw=3.5, label='Texas (ERCOT)'),
    Line2D([0], [0], color='#cccccc', lw=2.5, ls='--', dashes=(6, 3),
           label='Planned (T/TS/U/V)'),
    Line2D([0], [0], color='#cccccc', lw=2.0, ls=':', dashes=(1.5, 3),
           label='Planned (all)'),
]
ax.legend(handles=_legend_els, frameon=False, fontsize=14,
          loc='upper left', labelcolor='#444444', handlelength=2.4,
          borderpad=0, labelspacing=0.5)

ax.set_title('Cumulative Utility-Scale Battery Energy Capacity',
             fontsize=20, fontweight='normal', pad=16,
             loc='left', color=_TITLE_CLR)

fig.text(0.01, -0.03,
    'Source: EIA-860M April 2026.\n'
    'Operating = nameplate energy capacity (MWh) of units in service through Apr 2026.\n'
    'Planned GWh estimated using each BA\'s operating average duration '
    f'(CAISO {avg_dur_ca:.1f}h, ERCOT {avg_dur_tx:.1f}h) × planned MW.',
    fontsize=11, color=_NOTE_CLR, va='top')

plt.tight_layout()
os.makedirs(os.path.dirname(OUT_SVG), exist_ok=True)
fig.savefig(OUT_SVG, format='svg', bbox_inches='tight')
print(f'Saved: {OUT_SVG}')
plt.show()
plt.rcParams.update(plt.rcParamsDefault)
