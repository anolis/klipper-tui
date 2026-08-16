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

# Live view lifecycle: joining a run this app did not start, and leaving it.
import time
from klipper_tui.panels import bedmesh as bm_module

live = BedMeshPanel.__new__(BedMeshPanel)
live.algorithm = "bicubic"
live._count_seeded = True
live.live = {}
live.live_expected = None
live.live_joined = False
live._last_probe_at = 0.0
live.bounds = (10.0, 10.0, 185.0, 239.0)
live._redraw_live = lambda: None
live._render_heightmap = lambda matrix, lo, hi: "MESH"
live.query_one = lambda *a, **k: type(
    "Stub", (), {"update": lambda self, value: None})()

BASE_CFG = {"configfile": {"config": {"bed_mesh": {
    "algorithm": "bicubic", "probe_count": "10,10",
    "mesh_min": "10,10", "mesh_max": "185,239"}}}}


def mesh_status(matrix):
    payload = dict(BASE_CFG)
    payload["bed_mesh"] = {
        "profile_name": "default" if matrix else "",
        "probed_matrix": matrix or [[]],
        "profiles": {"default": {"points": [[0.1] * 10] * 10}},
    }
    return payload


live.start_live((10, 10), joined=True)
live.add_probe(10.0, 10.0, 0.05)
check("joined run is live", live.live_expected == (10, 10))
check("joined flag set", live.live_joined)

live.update_status(mesh_status(None))
check("stays live while the mesh is empty", live.live_expected is not None)

live.update_status(mesh_status([[0.01] * 10] * 10))
check("leaves live once the mesh is populated", live.live_expected is None,
      "a finished run must hand the display back")

live.start_live((10, 10), joined=True)
live._last_probe_at = time.monotonic() - 5
live.update_status(mesh_status(None))
check("stays live inside the idle window", live.live_expected is not None)

live._last_probe_at = time.monotonic() - (bm_module.PROBE_IDLE_TIMEOUT + 1)
live.update_status(mesh_status(None))
check("times out when probing goes quiet", live.live_expected is None,
      "an abandoned run must not pin the display forever")

for f in failures:
    print("FAIL", f)
print("bed mesh: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
