"""
Replace the SVG content inside each {=html} figure block in index.qmd
with the updated (title-stripped) versions from figs/.
SVGs are single-line in the QMD, so we match <svg ...>...</svg> positionally.
"""
import re

FIGS_DIR = "/Users/ashreeta/Downloads/Articles/articles/curtailment/figs"
QMD_PATH = "/Users/ashreeta/Downloads/Articles/articles/curtailment/index.qmd"

# Order must match the order figures appear in the QMD
SVG_FILES = [
    "fig_f1.svg",
    "fig_f2.svg",
    "fig_f1c.svg",
    "fig_seasonal_caiso_tab.svg",
    "fig_seasonal_ercot_tab.svg",
    "chart_e.svg",
    "fig_growth.svg",
    "chart_d.svg",
]

DEFAULT_STYLE = "width:100%;height:auto;display:block"

# Per-figure inline style overrides. Figures not listed here get DEFAULT_STYLE.
# chart_d.svg (Figure 4, CAISO Local vs System) is deliberately displayed at
# half width, centered, rather than full-width like the others.
STYLE_OVERRIDES = {
    "chart_d.svg": "width:50%;height:auto;display:block;margin:0 auto",
}

def read_svg(name):
    with open(f"{FIGS_DIR}/{name}") as f:
        svg = f.read().strip()
    style = STYLE_OVERRIDES.get(name, DEFAULT_STYLE)
    return svg.replace('style=""', f'style="{style}"', 1)

with open(QMD_PATH) as f:
    content = f.read()

# Find all SVG blocks and replace them in order
svg_pattern = re.compile(r'<svg\b[^>]*>.*?</svg>', re.DOTALL)
matches = list(svg_pattern.finditer(content))

if len(matches) != len(SVG_FILES):
    raise ValueError(f"Found {len(matches)} SVG blocks but expected {len(SVG_FILES)}")

# Replace from end to start so indices stay valid
result = content
for match, fname in zip(reversed(matches), reversed(SVG_FILES)):
    new_svg = read_svg(fname)
    result = result[:match.start()] + new_svg + result[match.end():]

with open(QMD_PATH, "w") as f:
    f.write(result)

print(f"✓ Swapped {len(SVG_FILES)} SVGs in {QMD_PATH}")
for i, (m, fname) in enumerate(zip(matches, SVG_FILES)):
    print(f"  [{i+1}] {fname}")
