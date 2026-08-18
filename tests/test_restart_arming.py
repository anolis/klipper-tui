"""Restarting a job must not home Z until the bed has been cleared.

Homing Z raises the bed on this class of printer, so doing it with the last
print still attached drives that print into the gantry. The old sequence
called print_start and then print_pause, which cannot help: by the time a job
reports itself as printing, its start gcode has already run G28, and Klipper
will not abandon a homing move to honour a pause.

So Restart now sends nothing except an X and Y home — neither of which moves
the bed — and remembers the file. Resume is what starts it.
"""

import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import klipper_tui.app as app_module

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


def body(method) -> str:
    """The source with its docstring removed.

    The docstrings here explain what the code deliberately does not do, so
    matching against them finds the opposite of what is meant.
    """
    source = inspect.getsource(method)
    doc = inspect.getdoc(method)
    if doc:
        for line in doc.splitlines():
            source = source.replace(line, "")
    return source


restart = body(app_module.KlipperTUI._restart_job)
home = body(app_module.KlipperTUI._home_xy_only)
start_armed = body(app_module.KlipperTUI._start_armed)

# -- what Restart may and may not do -------------------------------------------

if "self.client.print_start" in restart:
    failures.append("Restart starts the job; it must only arm it")
if "armed_restart = filename" not in restart:
    failures.append("Restart does not arm the job")
if "_home_xy_only" not in restart:
    failures.append("Restart does not home X and Y")

# Only Resume sends the job.
if "self.client.print_start" not in start_armed:
    failures.append("_start_armed does not start the job")

# -- homing must never touch Z -------------------------------------------------

for line in home.splitlines():
    stripped = line.strip()
    if not stripped.startswith(("await self.send", 'f"G', '"G')):
        continue
    if "G28" in stripped:
        if "Z" in stripped.split("G28")[1].upper().split("\\n")[0]:
            failures.append(f"the arming home includes Z: {stripped}")
        if "X" not in stripped or "Y" not in stripped:
            failures.append(f"the arming home is not X and Y: {stripped}")

check("a bare G28 would home everything, including Z",
      'send("G28")' in home, False)
check("X and Y are homed", 'send("G28 X Y")' in home, True)

# -- the clearance lift is bounded ---------------------------------------------

if "axis_maximum" not in home:
    failures.append("the lift does not check how much room is above")
if '"z" in homed' not in home:
    failures.append("the lift does not check that Z is homed first")


# -- the arming state drives the buttons ---------------------------------------

from klipper_tui.panels.status import StatusPanel

buttons = inspect.getsource(StatusPanel._set_job_buttons)
if "armed" not in buttons:
    failures.append("the job buttons ignore the armed state")

# Resume has to be reachable while armed, or the job can never be started.
class FakeApp:
    armed_restart = "a.gcode"


panel = StatusPanel.__new__(StatusPanel)
recorded = {}


class FakeButton:
    def __init__(self, name):
        self.name = name
        self.disabled = None


fakes = {name: FakeButton(name) for name in
         ("st-pause", "st-resume", "st-cancel", "st-restart")}
panel.query_one = lambda selector, _type=None: fakes[selector.lstrip("#")]
panel._armed = lambda: "a.gcode"
panel._set_job_buttons("complete", True)
check("Resume is offered while armed", fakes["st-resume"].disabled, False)
check("Cancel can disarm", fakes["st-cancel"].disabled, False)
check("Pause is not offered while nothing runs", fakes["st-pause"].disabled, True)

panel._armed = lambda: None
panel._set_job_buttons("complete", True)
check("Resume is not offered when idle and unarmed",
      fakes["st-resume"].disabled, True)

# -- what actually goes to the printer -----------------------------------------

class FakeClient:
    def __init__(self, status):
        self.status = status


def sent_for(homed, position, maximum):
    """The gcode _home_xy_only would send for a given toolhead state."""
    app = app_module.KlipperTUI.__new__(app_module.KlipperTUI)
    app.client = FakeClient({"toolhead": {
        "homed_axes": homed, "position": position, "axis_maximum": maximum}})
    commands = []

    async def send(script, *args, **kwargs):
        commands.append(script)

    app.send = send
    asyncio.run(app._home_xy_only())
    return commands


# Plenty of room above: lift, then home X and Y.
plenty = sent_for("xyz", [10.0, 10.0, 4.0, 0.0], [245.0, 260.0, 400.0, 0.0])
check("a lift and a home", len(plenty), 2)
check("the lift is relative and restores absolute",
      plenty[0].startswith("G91") and plenty[0].endswith("G90"), True)
check("the home is X and Y only", plenty[-1], "G28 X Y")
if "Z" in plenty[-1].replace("X Y", ""):
    failures.append("the home mentions Z")

# Near the top of the axis: no room, so no lift — but still home X and Y.
cramped = sent_for("xyz", [10.0, 10.0, 399.8, 0.0], [245.0, 260.0, 400.0, 0.0])
check("no lift when there is no room", cramped, ["G28 X Y"])

# Z not homed: a relative move has no known start, so skip it.
unhomed = sent_for("xy", [10.0, 10.0, 0.0, 0.0], [245.0, 260.0, 400.0, 0.0])
check("no lift when Z is not homed", unhomed, ["G28 X Y"])

# Missing figures must not raise.
missing = sent_for("xyz", [], [])
check("no lift without a position", missing, ["G28 X Y"])

# The lift never exceeds the room available.
tight = sent_for("xyz", [0.0, 0.0, 396.0, 0.0], [245.0, 260.0, 400.0, 0.0])
if len(tight) == 2:
    import re
    amount = float(re.search(r"Z([\d.]+)", tight[0]).group(1))
    if amount > 3.0:
        failures.append(f"the lift of {amount} would overrun the axis")


if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
