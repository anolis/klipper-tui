"""The cooldown prompt fires only when a running job is cancelled hot."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.app import KlipperTUI

app = KlipperTUI.__new__(KlipperTUI)
fired = []
app.call_later = lambda fn: fired.append("prompt")


def feed(state, extruder, bed):
    fired.clear()
    app._watch_print_state({
        "print_stats": {"state": state},
        "extruder": {"target": extruder},
        "heater_bed": {"target": bed},
    })
    return bool(fired)


CASES = [
    # name, sequence of (state, extruder target, bed target), expect prompt
    ("connect while already cancelled", [("cancelled", 250, 80)], False),
    ("printing to cancelled, hot", [("printing", 250, 80), ("cancelled", 250, 80)], True),
    ("paused to cancelled, hot", [("printing", 250, 80), ("paused", 250, 80),
                                  ("cancelled", 250, 80)], True),
    ("printing to cancelled, cold", [("printing", 0, 0), ("cancelled", 0, 0)], False),
    ("standby to cancelled", [("standby", 250, 80), ("cancelled", 250, 80)], False),
    ("finished normally", [("printing", 250, 80), ("complete", 250, 80)], False),
    ("errored", [("printing", 250, 80), ("error", 250, 80)], False),
    ("only the bed is on", [("printing", 0, 60), ("cancelled", 0, 60)], True),
]

failures = []
for name, steps, expected in CASES:
    app._print_state = None
    app._cooldown_pending = False
    prompted = False
    for state, extruder, bed in steps:
        prompted = feed(state, extruder, bed)
    if prompted != expected:
        failures.append(f"{name}: prompted={prompted} expected={expected}")

# A prompt already on screen must not be raised a second time.
app._print_state = "printing"
app._cooldown_pending = True
if feed("cancelled", 250, 80):
    failures.append("prompted while one was already pending")

for f in failures:
    print("FAIL", f)
print("cooldown: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
