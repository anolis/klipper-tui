"""Fan discovery, labelling, and the command each type needs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.moonraker import DISCOVERED_PREFIXES
from klipper_tui.panels.fans import (
    LABEL_WIDTH,
    FansPanel,
    controllable,
    fan_label,
    is_fan,
    speed_command,
)

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


# What counts as a fan.
for name in ("fan", "fan_generic board_fan", "heater_fan nozzle",
             "controller_fan mcu", "temperature_fan chamber"):
    check(f"{name} is a fan", is_fan(name))
for name in ("extruder", "heater_bed", "toolhead", "fan_speed_thing"):
    check(f"{name} is not a fan", not is_fan(name))

# Klipper drives these itself; offering controls would be a lie.
check("part fan is controllable", controllable("fan"))
check("generic fan is controllable", controllable("fan_generic board_fan"))
for name in ("heater_fan nozzle", "controller_fan mcu",
             "temperature_fan chamber"):
    check(f"{name} is automatic", not controllable(name))

# The part fan predates SET_FAN_SPEED and takes 0-255.
check("part fan off uses M107", speed_command("fan", 0) == "M107")
check("part fan half", speed_command("fan", 50) == "M106 S128",
      speed_command("fan", 50))
check("part fan full", speed_command("fan", 100) == "M106 S255",
      speed_command("fan", 100))
check("generic fan uses SET_FAN_SPEED",
      speed_command("fan_generic board_fan", 40)
      == "SET_FAN_SPEED FAN=board_fan SPEED=0.40",
      speed_command("fan_generic board_fan", 40))

# Labels have to fit beside the bar.
for name in ("fan", "fan_generic board_fan", "heater_fan nozzle_cooling_fan",
             "controller_fan an_absurdly_long_fan_name_here"):
    label = fan_label(name)
    check(f"label for {name} fits", len(label) < LABEL_WIDTH,
          f"{label!r} is {len(label)}")
check("readable label", fan_label("fan_generic board_fan") == "Board fan",
      fan_label("fan_generic board_fan"))

# Nudging stays inside 0-100.
panel = FansPanel.__new__(FansPanel)
panel.fans = ["fan"]
panel.speeds = {"fan": 95.0}
check("nudge up clamps", panel.nudged(0, 10) == 100.0, panel.nudged(0, 10))
panel.speeds = {"fan": 5.0}
check("nudge down clamps", panel.nudged(0, -10) == 0.0, panel.nudged(0, -10))
check("unknown index is safe", panel.fan_at(9) is None)

# The client has to subscribe to fans it cannot know the names of up front.
for prefix in ("fan_generic ", "heater_fan ", "controller_fan ",
               "temperature_fan "):
    check(f"{prefix} is discovered", prefix in DISCOVERED_PREFIXES)

for f in failures:
    print("FAIL", f)
print("fans: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
