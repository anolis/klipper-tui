"""Panning and click-to-centre, in both viewers.

The two used opposite sign conventions, which is how the toolpath viewer's up
and down buttons ended up inverted. Positive dy means the view moves up, in
both, and one button mapping serves them.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.gcode import Segment, Toolpath
from klipper_tui.panels.gcodeview import GcodeViewPanel
from klipper_tui.panels.position import PositionPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


# -- toolpath viewer --------------------------------------------------------

def toolpath_panel():
    panel = GcodeViewPanel.__new__(GcodeViewPanel)
    panel.zoom = 1.0
    panel.pan = [0.0, 0.0]
    panel.file_position = 10 ** 9
    panel.head = None
    panel._cache_key = None
    panel._cache = []
    panel._redraw = lambda: None
    path = Toolpath()
    for i in range(16):
        path.segments.append(
            Segment(100 + i * 0.2, 130, 100 + i * 0.2 + 0.2, 130, True, 0))
    panel.toolpath = path
    panel.frame = (60.0, 60.0, 180.0, 200.0)
    return panel


def mark_row(panel):
    for index, row in enumerate(panel._render_toolpath(60, 20)):
        if re.sub(r"\[[^\]]*\]", "", row).strip():
            return index
    return None


panel = toolpath_panel()
centre = mark_row(panel)
panel.pan = [0.0, 0.08]
up = mark_row(panel)
panel.pan = [0.0, -0.08]
down = mark_row(panel)
check("toolpath: positive dy moves the view up", up < centre,
      f"{centre} -> {up}")
check("toolpath: negative dy moves it down", down > centre,
      f"{centre} -> {down}")

# -- 3D view ----------------------------------------------------------------

space = PositionPanel.__new__(PositionPanel)
space.limits = ([0.0, 0.0, 0.0], [245.0, 260.0, 400.0])
space.yaw, space.tilt, space.zoom = 0.6, 0.5, 1.0


def middle_y(pan_y):
    space.pan = [0.0, pan_y]
    return space._project(0.5, 0.5, 0.5, space._fit(200, 200))[1]


base = middle_y(0.0)
check("3D: positive dy moves the view up", middle_y(0.08) < base)
check("3D: negative dy moves it down", middle_y(-0.08) > base)
check("both agree on direction",
      (up < centre) == (middle_y(0.08) < base),
      "one mapping has to serve both panels")

# -- click to centre --------------------------------------------------------

panel = toolpath_panel()
# Put the mark well away from the middle, or there is nothing to centre.
offset = Toolpath()
for i in range(16):
    offset.segments.append(
        Segment(100 + i * 0.2, 175, 100 + i * 0.2 + 0.2, 175, True, 0))
panel.toolpath = offset
before = mark_row(panel)
check("fixture really is off centre", abs(before - 10) > 2, f"row {before}")
# Click where the mark is; it should end up in the middle.
panel.centre_on(0.3, before / 20)
after = mark_row(panel)
check("clicking centres vertically", abs(after - 10) < abs(before - 10),
      f"{before} -> {after}")
check("clicking lands it in the middle", abs(after - 10) <= 1, f"{after}")

# A click already at the centre should barely move anything.
panel = toolpath_panel()
still = mark_row(panel)
panel.centre_on(0.5, 0.5)
check("centre click is a no-op vertically", mark_row(panel) == still)

for f in failures:
    print("FAIL", f)
print("pan: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
