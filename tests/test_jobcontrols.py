"""Job control gating and the offline overlay's reasons."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.offline import STATE_HELP
from klipper_tui.panels.status import StatusPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


class FakeButton:
    def __init__(self):
        self.disabled = False


panel = StatusPanel.__new__(StatusPanel)
buttons = {f"st-{n}": FakeButton() for n in
           ("pause", "resume", "cancel", "restart")}
panel.query_one = lambda selector, *a: buttons[selector.lstrip("#")]


def enabled_for(state, has_file):
    panel._set_job_buttons(state, has_file)
    return {name.removeprefix("st-")
            for name, button in buttons.items() if not button.disabled}


CASES = [
    ("printing", True, {"pause", "cancel", "restart"}),
    ("paused", True, {"resume", "cancel", "restart"}),
    ("complete", True, {"restart"}),
    ("cancelled", True, {"restart"}),
    ("standby", False, set()),
    # A finished job with no file left cannot be restarted.
    ("complete", False, set()),
]
for state, has_file, expected in CASES:
    got = enabled_for(state, has_file)
    check(f"{state} (file={has_file})", got == expected, f"{got} != {expected}")

# Pausing a job that is not running would just error at the printer.
check("cannot pause when not printing", "pause" not in enabled_for("paused", True))
check("cannot resume while printing", "resume" not in enabled_for("printing", True))

# Every state that keeps the printer unusable should explain itself.
for state in ("shutdown", "error", "startup", "disconnected"):
    check(f"offline help for {state}", bool(STATE_HELP.get(state)))

for f in failures:
    print("FAIL", f)
print("job controls: all checks passed" if not failures
      else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
