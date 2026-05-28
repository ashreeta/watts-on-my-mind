import re, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap

# Vivid orange-blue diverging colormap
cmap = LinearSegmentedColormap.from_list('orbu', [
    ( 20/255,  70/255, 185/255),  # deep blue  (negative max)
    (  1.0,     1.0,    1.0  ),   # white      (zero)
    (255/255, 140/255,   0/255),  # vivid orange (positive max)
], N=512)

MTK = [
    (0.0,      "Jan"), (0.08493, "Feb"), (0.16164, "Mar"),
    (0.24657,  "Apr"), (0.32876, "May"), (0.41369, "Jun"),
    (0.49589,  "Jul"), (0.58082, "Aug"), (0.66575, "Sep"),
    (0.74794,  "Oct"), (0.83287, "Nov"), (0.91506, "Dec"),
]
DAYS, HRS = 365, 24

def extract(filepath):
    with open(filepath) as f:
        content = f.read()
    cmax = float(re.search(r'const CMAX\s*=\s*([\d.]+)', content).group(1))
    panels_str = re.search(r'const panels\s*=\s*(\[.+\]);', content).group(1)
    panels = json.loads(panels_str)
    return cmax, panels

def render_panel(ax, panel, cmax, show_y=False):
    data = np.array(panel['data'], dtype=float).reshape(DAYS, HRS)
    im = ax.imshow(data, cmap=cmap, vmin=-cmax, vmax=cmax,
                   aspect='auto', interpolation='nearest', origin='upper')

    ax.text(0.5, 1.04, panel['entity'], transform=ax.transAxes,
            ha='center', va='bottom', fontsize=8, fontweight='bold', color='#333',
            clip_on=False)

    ax.set_xticks([0, 6, 12, 18, 23])
    ax.set_xticklabels(['0h', '6h', '12h', '18h', '23h'], fontsize=6.5, color='#aaa')
    ax.tick_params(axis='x', length=2, color='#ccc', pad=2)

    if show_y:
        yticks  = [int(round(frac * (DAYS - 1))) for frac, _ in MTK]
        ylabels = [lbl for _, lbl in MTK]
        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels, fontsize=7, color='#aaa')
        ax.tick_params(axis='y', length=0, pad=3)
    else:
        ax.set_yticks([])

    for spine in ax.spines.values():
        spine.set_edgecolor('#e4e2da')
        spine.set_linewidth(0.6)

    return im

def add_colorbar(fig, im_ref, cax, cmax):
    half = int(cmax / 2)
    cb = fig.colorbar(im_ref, cax=cax)
    cb.set_ticks([-cmax, -half, 0, half, cmax])
    cb.set_ticklabels([f'−{int(cmax)}%', f'−{half}%', '0%',
                       f'+{half}%', f'+{int(cmax)}%'])
    cb.ax.tick_params(labelsize=6.5, length=2, color='#ccc', labelcolor='#aaa', pad=2)
    cb.outline.set_edgecolor('#e4e2da')
    cb.outline.set_linewidth(0.6)
    cb.ax.set_title('% chg', fontsize=6.5, color='#999', pad=4)

def make_svg(widget_file, out_file, grid=None, fig_width=None, fig_height=None):
    """
    grid: list of ints specifying panels per row, e.g. [3, 2] for 5-panel 3+2 layout.
          None = single row with all panels.
    """
    cmax, panels = extract(widget_file)
    n = len(panels)

    if grid is None:
        grid = [n]

    # Build row index lists
    rows, idx = [], 0
    for count in grid:
        end = min(idx + count, n)
        rows.append(list(range(idx, end)))
        idx = end
        if idx >= n:
            break

    n_rows      = len(rows)
    max_per_row = max(len(r) for r in rows)

    # Figure geometry (inches)
    panel_w = 2.15
    yax_w   = 0.40
    cb_w    = 0.52
    _fig_h  = fig_height or (3.6 if n_rows == 1 else n_rows * 2.9 + 0.3)
    _fig_w  = fig_width  or (yax_w + max_per_row * panel_w + cb_w)

    fig = plt.figure(figsize=(_fig_w, _fig_h), facecolor='white')

    # Use 12 virtual columns so any number of panels can be centered
    NCOLS = 12
    left   = yax_w / _fig_w
    right  = 1 - cb_w / _fig_w
    top    = 0.90 if n_rows == 1 else 0.93
    bottom = 0.09

    hspace = 0.20 if n_rows > 1 else 0
    gs = gridspec.GridSpec(
        n_rows, NCOLS,
        left=left, right=right,
        top=top, bottom=bottom,
        hspace=hspace,
        wspace=0.05,
    )

    im_ref = None
    for row_i, row_panels in enumerate(rows):
        row_n      = len(row_panels)
        col_span   = NCOLS // max_per_row          # virtual cols each panel occupies
        row_offset = (NCOLS - row_n * col_span) // 2  # centering offset

        for col_i, panel_idx in enumerate(row_panels):
            c0 = row_offset + col_i * col_span
            ax = fig.add_subplot(gs[row_i, c0 : c0 + col_span])
            im = render_panel(ax, panels[panel_idx], cmax, show_y=(col_i == 0))
            im_ref = im

    # Colorbar spanning height of one row
    span = top - bottom
    row_h = span / (n_rows + hspace * (n_rows - 1))
    cb_ax = fig.add_axes([right + 0.008, top - row_h, 0.013, row_h])
    add_colorbar(fig, im_ref, cb_ax, cmax)

    fig.savefig(out_file, format='svg', bbox_inches='tight',
                facecolor='white', metadata={'Creator': ''})
    plt.close(fig)
    print(f"  wrote {out_file}")

base = '/Users/ashreeta/Downloads/Articles/articles/eia-demand/widgets/'
print("Generating heatmap SVGs...")
make_svg(base + 'heatmap-ny-nyis.html', base + 'heatmap-ny-nyis.svg', grid=[3, 2])
make_svg(base + 'heatmap-ne-isne.html', base + 'heatmap-ne-isne.svg', fig_width=3.2)
make_svg(base + 'heatmap-cal-caiso.html', base + 'heatmap-cal-caiso.svg')
print("Done.")
