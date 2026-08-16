"""Every panel must survive the status stream, from the very first update.

The status panel once raised AttributeError on every update, because an
attribute was only created when job metadata arrived. It sat outside the
per-panel guard in the fan-out, so that one exception skipped every panel
after it: the bed mesh, the fans, the macros, the toolhead and the rest
silently stopped updating while the interface still looked alive.

The panels are mounted here rather than merely constructed, because an
unmounted panel cannot query its own children and would fail for a reason the
app already tolerates.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())

from textual.app import App, ComposeResult

import klipper_tui.app as app_module
from klipper_tui.panels.bedmesh import BedMeshPanel
from klipper_tui.panels.extruder import ExtruderPanel
from klipper_tui.panels.fans import FansPanel
from klipper_tui.panels.gcodeview import GcodeViewPanel
from klipper_tui.panels.machine import MachinePanel
from klipper_tui.panels.macros import MacrosPanel
from klipper_tui.panels.objects import ObjectsPanel
from klipper_tui.panels.position import PositionPanel
from klipper_tui.panels.status import StatusPanel
from klipper_tui.panels.temperature import TemperaturePanel
from klipper_tui.panels.toolhead import ToolheadPanel
from klipper_tui.panels.tuning import TuningPanel
from klipper_tui.theming import DEFAULT_THEME, register

failures = []

# What Moonraker pushes mid-print, trimmed to the fields the panels read.
LIVE = {
    "print_stats": {"state": "printing", "filename": "a.gcode",
                    "total_duration": 3200.0, "print_duration": 3100.0,
                    "filament_used": 1712.0, "info": {}},
    "virtual_sdcard": {"progress": 0.42, "is_active": True,
                       "file_position": 120000, "file_size": 285000},
    "display_status": {"progress": 0.42},
    "toolhead": {"position": [1.0, 2.0, 3.0, 4.0], "homed_axes": "xyz",
                 "max_velocity": 500.0, "max_accel": 2000.0,
                 "square_corner_velocity": 5.0, "minimum_cruise_ratio": 0.5,
                 "axis_maximum": [245.0, 260.0, 400.0, 0.0]},
    "gcode_move": {"speed_factor": 1.5, "extrude_factor": 1.0,
                   "homing_origin": [0.0, 0.0, 0.0, 0.0],
                   "gcode_position": [1.0, 2.0, 3.0, 4.0]},
    "extruder": {"temperature": 215.0, "target": 215.0, "power": 0.5,
                 "can_extrude": True},
    "heater_bed": {"temperature": 65.0, "target": 65.0, "power": 0.1},
    "fan": {"speed": 0.0},
    "motion_report": {"live_position": [1.0, 2.0, 3.0, 4.0],
                      "live_velocity": 40.0},
    "bed_mesh": {"profile_name": "default",
                 "probed_matrix": [[0.0, 0.1], [0.1, 0.0]],
                 "profiles": {"default": {"points": [[0.0, 0.1],
                                                     [0.1, 0.0]]}}},
    "configfile": {
        "config": {"bed_mesh": {"algorithm": "bicubic",
                                "probe_count": "10, 10",
                                "mesh_min": "10, 10",
                                "mesh_max": "185, 239"}},
        "settings": {"bltouch": {"z_offset": 0.85}, "printer": {}},
    },
    "gcode_macro START_PRINT": {},
    "idle_timeout": {"state": "Printing"},
    "webhooks": {"state": "ready"},
}

SIMPLE = [TemperaturePanel, ExtruderPanel, BedMeshPanel, PositionPanel,
          TuningPanel, GcodeViewPanel, ToolheadPanel, MachinePanel,
          FansPanel, MacrosPanel, ObjectsPanel]


def build(panel_type):
    return panel_type(1000.0) if panel_type is ExtruderPanel else panel_type()


class Harness(App):
    CSS_PATH = str(Path(__file__).resolve().parent.parent
                   / "klipper_tui" / "app.tcss")

    def compose(self) -> ComposeResult:
        yield StatusPanel()
        for panel_type in SIMPLE:
            yield build(panel_type)

    def on_mount(self) -> None:
        register(self)
        self.theme = DEFAULT_THEME


async def run() -> None:
    app = Harness()
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        for label, status in (("an empty status", {}), ("a live print", LIVE)):
            for panel in app.query(StatusPanel):
                try:
                    panel.update_status(status, "ready")
                except Exception as error:
                    failures.append(f"StatusPanel on {label}: {error!r}")
            for panel_type in SIMPLE:
                for panel in app.query(panel_type):
                    try:
                        panel.update_status(status)
                    except Exception as error:
                        failures.append(
                            f"{panel_type.__name__} on {label}: {error!r}")
            await pilot.pause()

        # The bed mesh has to have read the printer's algorithm, or a probe
        # count the printer would accept gets rejected against the default.
        mesh = app.query(BedMeshPanel).first()
        if mesh.algorithm != "bicubic":
            failures.append(
                f"bed mesh algorithm is {mesh.algorithm!r}, not the "
                f"configured 'bicubic'")


asyncio.run(run())

# Every panel the app feeds must be in the table it iterates.
covered = set(app_module.KlipperTUI.STATUS_PANELS)
for panel_type in SIMPLE:
    if panel_type not in covered:
        failures.append(f"{panel_type.__name__} is not in STATUS_PANELS")

if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
