"""Nothing that would wreck a running print goes through unasked."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.app import DISRUPTIVE, KlipperTUI

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


app = KlipperTUI.__new__(KlipperTUI)


class FakeClient:
    def __init__(self, state, filename=""):
        self.status = {"print_stats": {"state": state, "filename": filename}}


# Everything that moves the machine or interrupts the job must be guarded.
MUST_GUARD = [
    "th-home-all", "th-home-x", "th-home-y", "th-home-z",
    "th-x-neg", "th-x-pos", "th-y-neg", "th-y-pos", "th-z-neg", "th-z-pos",
    "th-motors-off", "th-ztilt", "th-z-save",
    "ex-extrude", "ex-retract", "ex-load", "ex-unload",
    "bm-calibrate", "bm-clear", "bm-save",
]
for bid in MUST_GUARD:
    check(f"{bid} is guarded", bid in DISRUPTIVE, "would go straight through")

# Things you legitimately reach for mid-print must not nag.
MUST_NOT_GUARD = [
    "tp-set", "tp-preset-PLA", "tp-cooldown",          # temperatures
    "tn-speed-up", "tn-flow-down", "tn-speed-set-100",  # speed and flow
    "th-znudge-0", "th-znudge-3", "th-z-reset",         # babystepping
    "fn-set-0-50", "fn-up-0", "fn-apply-0",             # fans
    "st-pause", "st-resume", "st-cancel",               # job control itself
    "gv-follow", "gv-next", "ps-spin", "wc-toggle",     # views
]
for bid in MUST_NOT_GUARD:
    check(f"{bid} is not guarded", bid not in DISRUPTIVE,
          "would ask needlessly during a print")

# The guard only applies while a job is live.
for state, expected in (("printing", True), ("paused", True),
                        ("standby", False), ("complete", False),
                        ("cancelled", False), ("error", False)):
    app.client = FakeClient(state)
    check(f"live during {state} is {expected}",
          app._print_is_live() is expected, f"{state}")

app.client = FakeClient("printing")
check("every guarded action has a description",
      all(DISRUPTIVE[b] for b in DISRUPTIVE))

for f in failures:
    print("FAIL", f)
print("guard: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
