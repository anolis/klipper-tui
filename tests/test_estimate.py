"""Two estimates of the finish, and which one to lead with."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.estimate import (MIN_SPAN, Estimator, best,
                                  filament_remaining, slicer_remaining)

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


def close(label, got, want, tolerance):
    if got is None or abs(got - want) > tolerance:
        failures.append(f"{label}: got {got!r}, wanted about {want}")


# -- the measured rate ---------------------------------------------------------

e = Estimator()
check("nothing to go on yet", e.remaining(), None)

e.record(0.0, 0.0)
check("one sample is not a rate", e.remaining(), None)

# Too short a span to divide by.
e.record(MIN_SPAN / 2, 0.01)
check("too short a span", e.remaining(), None)

# A steady 1% of the file per 10s: 100s a percent-hundred, so at 20% there
# are 800 seconds left.
steady = Estimator()
for i in range(21):
    steady.record(i * 10.0, i * 0.01)
close("steady rate", steady.remaining(), 800.0, 1.0)
close("rate per second", steady.rate(), 0.001, 1e-6)

# A pause: the file stops moving, so there is no rate to project.
paused = Estimator()
for i in range(30):
    paused.record(i * 10.0, 0.4)
check("a paused job has no rate", paused.remaining(), None)

# Speeding up should be noticed, because only the recent window counts.
ramp = Estimator(window=100.0)
for i in range(11):            # slow: 0.1% every 10s
    ramp.record(i * 10.0, i * 0.001)
slow = ramp.remaining()
for i in range(1, 11):         # then ten times faster
    ramp.record(100.0 + i * 10.0, 0.01 + i * 0.01)
fast = ramp.remaining()
if slow is None or fast is None or fast >= slow / 2:
    failures.append(f"a speed-up was not noticed: {slow} -> {fast}")

# Progress going backwards means a different job; the old rate is worthless.
restarted = Estimator()
for i in range(21):
    restarted.record(i * 10.0, i * 0.03)
restarted.record(210.0, 0.0)
check("a restart clears the history", restarted.remaining(), None)

# Out-of-range figures are ignored rather than poisoning the rate.
odd = Estimator()
odd.record(0.0, -0.5)
odd.record(10.0, 1.5)
check("nonsense progress is ignored", odd.remaining(), None)


# -- the slicer, and filament --------------------------------------------------

check("slicer counts down", slicer_remaining({"estimated_time": 3600}, 600), 3000)
check("slicer never goes negative",
      slicer_remaining({"estimated_time": 100}, 500), 0.0)
check("no slicer figure", slicer_remaining({}, 600), None)
check("a zero estimate is not an estimate",
      slicer_remaining({"estimated_time": 0}, 600), None)

close("filament halfway",
      filament_remaining({"filament_used": 500}, {"filament_total": 1000}, 600),
      600.0, 1.0)
check("no filament figures", filament_remaining({}, {}, 600), None)


# -- which one leads -----------------------------------------------------------

check("early on, the slicer leads",
      best(measured=900.0, slicer=1200.0, filament=None,
           elapsed=30.0, progress=0.01)[1], "slicer")
check("once under way, the measured rate leads",
      best(measured=900.0, slicer=1200.0, filament=None,
           elapsed=600.0, progress=0.4)[1], "measured")
check("the measured rate is used even early if there is nothing else",
      best(measured=900.0, slicer=None, filament=None,
           elapsed=30.0, progress=0.01)[1], "measured")
check("filament is the next fallback",
      best(measured=None, slicer=None, filament=700.0,
           elapsed=600.0, progress=0.4)[1], "filament")
check("file position is the last resort",
      best(measured=None, slicer=None, filament=None,
           elapsed=600.0, progress=0.4)[1], "file")
check("nothing at all",
      best(measured=None, slicer=None, filament=None,
           elapsed=5.0, progress=0.0), (0.0, ""))

# -- the panels agree ----------------------------------------------------------
#
# The header and the status panel both show a time left. Two different answers
# on one screen is worse than either, so they go through the same function.

import inspect

from klipper_tui.panels.header import KlipperHeader
from klipper_tui.panels.status import StatusPanel

for owner, method in ((KlipperHeader, KlipperHeader.update_status),
                      (StatusPanel, StatusPanel._remaining)):
    body = inspect.getsource(method)
    if "estimate.best" not in body:
        failures.append(f"{owner.__name__} does not use estimate.best")
    if "self.app.estimator" not in body:
        failures.append(f"{owner.__name__} does not use the shared estimator")

# An unmounted panel must not explode: self.app raises rather than returning
# None, and the geometry tests build panels that way on purpose.
bare = StatusPanel.__new__(StatusPanel)
bare.job_meta = {"estimated_time": 3600}
try:
    got, from_where = bare._remaining({}, {}, 600.0, 50.0)
    if from_where != "slicer" or abs(got - 3000) > 1:
        failures.append(f"unmounted panel gave {got!r} from {from_where!r}")
except Exception as error:
    failures.append(f"unmounted panel raised: {error!r}")


if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
