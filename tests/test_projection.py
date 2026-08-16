"""The build volume must not render mirrored.

Screen y grows downward, so the depth term needs negating along with height.
Without it the projection is left-handed and the volume appears flipped.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.position import PositionPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


panel = PositionPanel.__new__(PositionPanel)
panel.limits = ([0.0, 0.0, 0.0], [245.0, 260.0, 400.0])
panel.zoom = 1.0
panel.pan = [0.0, 0.0]


def project(u, v, w):
    return panel._project(u, v, w, panel._fit(400, 400))


# Viewed head-on, the bed's axes must land the obvious way round.
panel.yaw, panel.tilt = 0.0, 0.5
front_left = project(0, 0, 0)
front_right = project(1, 0, 0)
back_left = project(0, 1, 0)
above = project(0, 0, 1)

check("X+ draws to the right", front_right[0] > front_left[0],
      f"{front_left[0]} -> {front_right[0]}")
check("Y+ (back of bed) draws higher", back_left[1] < front_left[1],
      f"{front_left[1]} -> {back_left[1]}")
check("Z+ draws higher", above[1] < front_left[1],
      f"{front_left[1]} -> {above[1]}")

# Handedness must hold from every viewpoint, not just head-on.
mirrored = []
z_wrong = []
for tilt in (0.2, 0.5, 0.9, 1.2):
    panel.tilt = tilt
    for step in range(24):
        panel.yaw = step * math.pi / 12
        origin = project(0, 0, 0)
        x_axis = project(1, 0, 0)
        y_axis = project(0, 1, 0)
        # Flip screen y so the cross product is in normal orientation.
        vx = (x_axis[0] - origin[0], -(x_axis[1] - origin[1]))
        vy = (y_axis[0] - origin[0], -(y_axis[1] - origin[1]))
        if vx[0] * vy[1] - vx[1] * vy[0] <= 0:
            mirrored.append((round(tilt, 2), round(panel.yaw, 2)))
        if not project(0.5, 0.5, 1.0)[1] < project(0.5, 0.5, 0.0)[1]:
            z_wrong.append((round(tilt, 2), round(panel.yaw, 2)))

check("never mirrored at any viewpoint", not mirrored, f"{mirrored[:5]}")
check("Z always points up", not z_wrong, f"{z_wrong[:5]}")

for f in failures:
    print("FAIL", f)
print("projection: all checks passed" if not failures
      else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
