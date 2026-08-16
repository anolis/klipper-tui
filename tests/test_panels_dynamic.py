"""Panels built from whatever the printer happens to expose."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.console import ConsolePanel
from klipper_tui.panels.macros import is_hidden, macro_names
from klipper_tui.panels.objects import object_name
from klipper_tui.settings import DASHBOARD_PANELS, PANEL_MIN_WIDTH

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


# -- macro discovery -----------------------------------------------------------

status = {
    "gcode_macro START_PRINT": {},
    "gcode_macro END_PRINT": {},
    "gcode_macro PAUSE": {},
    "gcode_macro _PARK": {},
    "extruder": {},
    "toolhead": {},
}
check("macros offered", macro_names(status), ["END_PRINT", "START_PRINT"])
check("underscore hidden", is_hidden("_PARK"), True)
check("pause hidden", is_hidden("pause"), True)
check("normal shown", is_hidden("LOAD_FILAMENT"), False)
check("no macros", macro_names({"extruder": {}}), [])


# -- console completion --------------------------------------------------------

console = ConsolePanel.__new__(ConsolePanel)
console.set_commands(["BED_MESH_CALIBRATE", "BED_MESH_CLEAR", "G28", "G28.1"])

check("common prefix", console.complete("BED_"), ("BED_MESH_C", [
    "BED_MESH_CALIBRATE", "BED_MESH_CLEAR"]))
check("unique match", console.complete("BED_MESH_CA"),
      ("BED_MESH_CALIBRATE ", []))
check("case insensitive", console.complete("g28")[0], "G28")
check("no match is left alone", console.complete("ZZZ"), ("ZZZ", []))
check("empty is left alone", console.complete(""), ("", []))
check("args are not completed", console.complete("G28 X"), ("G28 X", []))
# Nothing known yet: completion must not blow up before the command list loads.
blank = ConsolePanel.__new__(ConsolePanel)
blank.commands = []
check("no command list", blank.complete("G2"), ("G2", []))


# -- exclude object ------------------------------------------------------------

check("dict object", object_name({"name": "Cube", "center": [1, 2]}), "Cube")
check("plain string", object_name("Cube"), "Cube")
check("nameless", object_name({}), "?")


# -- every dashboard panel has a width -----------------------------------------

for key in DASHBOARD_PANELS:
    if key not in PANEL_MIN_WIDTH:
        failures.append(f"panel {key!r} has no minimum width")


if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
