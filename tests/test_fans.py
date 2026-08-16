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

# Typed speeds are validated before anything is sent.
class Field:
    def __init__(self, value=""):
        self.value = value


class Panel(FansPanel):
    def __init__(self, typed):
        self.fans = ["fan"]
        self.speeds = {"fan": 0.0}
        self.fields = {"#fn-in-0": Field(typed)}
        self.notes = []

    def query_one(self, selector, *args):
        return self.fields[selector]

    def note(self, message):
        self.notes.append(message)


check("accepts a whole number", Panel("37").read_custom(0) == 37.0)
check("accepts a fraction", Panel("12.5").read_custom(0) == 12.5)
check("accepts zero", Panel("0").read_custom(0) == 0.0)
check("accepts full", Panel("100").read_custom(0) == 100.0)

for bad, why in (("150", "above 100"), ("-5", "below zero"),
                 ("abc", "not a number"), ("", "empty")):
    panel = Panel(bad)
    check(f"rejects {why}", panel.read_custom(0) is None, f"{bad!r}")
    check(f"explains {why}", any(panel.notes), f"{bad!r} gave no message")

check("input id maps to a row",
      Panel("").index_of_input("fn-in-3") == 3)
check("other inputs are ignored",
      Panel("").index_of_input("tn-speed-input") is None)

for f in failures:
    print("FAIL", f)
print("fans: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
