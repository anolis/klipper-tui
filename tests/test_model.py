"""Model buildout: only deposited material is recorded."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.position import PositionPanel

panel = PositionPanel.__new__(PositionPanel)
panel.model = set()
panel.show_model = True
panel.voxel_mm = 2.0
panel.max_voxels = 6000
panel._last_e = None
panel._job = None

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


def feed(state, filename, x, y, z, e):
    panel._record_motion({
        "print_stats": {"state": state, "filename": filename},
        "motion_report": {"live_position": [x, y, z, e]},
    })


# Print a cylinder.
e = 0.0
for layer in range(40):
    z = 0.2 + layer * 1.5
    for i in range(40):
        a = i / 40 * 2 * math.pi
        e += 0.5
        feed("printing", "cyl.gcode", 122 + 35 * math.cos(a),
             130 + 35 * math.sin(a), z, e)

check("material recorded", len(panel.model) > 500, f"{len(panel.model)} voxels")
layers = {v[2] for v in panel.model}
check("multiple layers", len(layers) > 20, f"{len(layers)} layers")

# Nothing should be deposited by these.
count = len(panel.model)
feed("printing", "cyl.gcode", 10, 10, 5, e - 5)      # retraction
feed("printing", "cyl.gcode", 20, 20, 5, e - 5)      # travel, E unchanged
check("travel and retraction ignored", len(panel.model) == count,
      f"grew by {len(panel.model) - count}")

feed("standby", "cyl.gcode", 30, 30, 5, e + 99)      # not printing
check("idle motion ignored", len(panel.model) == count)

feed("printing", "next.gcode", 30, 30, 5, 1.0)       # different job
check("new job resets", len(panel.model) == 0, f"{len(panel.model)} left")

# The cap must hold, or a long print grows without bound.
panel._job = "big.gcode"
panel._last_e = 0.0
panel.max_voxels = 50
for i in range(500):
    feed("printing", "big.gcode", i % 200, (i * 7) % 200, i % 100, float(i + 1))
check("voxel cap respected", len(panel.model) <= 50, f"{len(panel.model)} voxels")

for f in failures:
    print("FAIL", f)
print("model: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
