"""Bed mesh probe parsing, grid placement, and the fixed gradient."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.bedmesh import GRADIENT, PROBE_LINE, BedMeshPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


# The heightmap encodes measurements, so its scale must not follow the theme.
check("gradient is literal",
      all(c.startswith("#") for c in GRADIENT),
      f"non-literal stops: {[c for c in GRADIENT if not c.startswith('#')]}")

# Both Klipper console wordings, old and current.
cases = [
    ("// probe: at 10.000,10.000 bed will contact at z=1.234567",
     (10.0, 10.0, 1.234567)),
    ("probe at 185.000,239.000 is z=-0.048000", (185.0, 239.0, -0.048)),
    ("// probe: at 97.500,124.500 bed will contact at z=0.012000",
     (97.5, 124.5, 0.012)),
]
for line, expected in cases:
    m = PROBE_LINE.search(line)
    check("probe line parses", m is not None, line)
    if m:
        got = tuple(float(m.group(i)) for i in (1, 2, 3))
        check("probe values", got == expected, f"{got} != {expected}")
check("ignores unrelated", PROBE_LINE.search("Klipper state: Ready") is None)

# Serpentine probing must land on distinct cells.
panel = BedMeshPanel.__new__(BedMeshPanel)
panel.live = {}
panel.live_expected = (10, 10)
panel.bounds = (10.0, 10.0, 185.0, 239.0)
panel._redraw_live = lambda: None
min_x, min_y, max_x, max_y = panel.bounds
placed = 0
for row in range(10):
    cols = range(10) if row % 2 == 0 else reversed(range(10))
    for col in cols:
        x = min_x + (max_x - min_x) * col / 9
        y = min_y + (max_y - min_y) * row / 9
        placed += bool(panel.add_probe(x, y, 0.1 * math.sin(col)))
check("all points accepted", placed == 100, f"placed {placed}")
check("no cell collisions", len(panel.live) == 100, f"cells {len(panel.live)}")

# Klipper's own probe_count constraints.
panel.algorithm = "bicubic"
check("bicubic 100x100 ok", panel.validate_count((100, 100)) is None)
check("bicubic 3x10 rejected", panel.validate_count((3, 10)) is not None)
check("below minimum rejected", panel.validate_count((2, 2)) is not None)
panel.algorithm = "lagrange"
check("lagrange >6 rejected", panel.validate_count((10, 10)) is not None)
check("lagrange 6x6 ok", panel.validate_count((6, 6)) is None)

for f in failures:
    print("FAIL", f)
print("bed mesh: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
