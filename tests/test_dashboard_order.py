"""Panels can be reordered, and the order survives a bad or stale file."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A scratch config, so a developer's own settings are never touched.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from klipper_tui.settings import DASHBOARD_PANELS, Settings, config_path

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


settings = Settings()
check("defaults to the declared order",
      settings.ordered(), list(DASHBOARD_PANELS))

first, second, third = settings.ordered()[:3]

check("moving down swaps with the next", settings.move(first, 1), True)
check("order after moving down", settings.ordered()[:2], [second, first])

check("moving up swaps with the previous", settings.move(first, -1), True)
check("order after moving back", settings.ordered()[:3],
      [first, second, third])

check("the top cannot move up", settings.move(first, -1), False)
check("the bottom cannot move down",
      settings.move(settings.ordered()[-1], 1), False)
check("an unknown panel does not move", settings.move("nonsense", 1), False)
check("a refused move leaves the order alone",
      settings.ordered(), list(DASHBOARD_PANELS))

# Moving to the very top from the middle, one step at a time.
target = settings.ordered()[5]
while settings.ordered().index(target) > 0:
    settings.move(target, -1)
check("walked to the top", settings.ordered()[0], target)
check("nothing was lost on the way",
      sorted(settings.ordered()), sorted(DASHBOARD_PANELS))

# -- persistence ---------------------------------------------------------------

settings.save()
check("the order is reloaded", Settings().ordered(), settings.ordered())

# -- a file written by a different version -------------------------------------

def reload_with(order):
    data = json.loads(config_path().read_text())
    data["dashboard_order"] = order
    config_path().write_text(json.dumps(data))
    return Settings()

fresh = reload_with(["fans", "status"])
check("a partial order keeps its lead", fresh.ordered()[:2], ["fans", "status"])
check("a partial order still lists everything",
      sorted(fresh.ordered()), sorted(DASHBOARD_PANELS))

fresh = reload_with(["fans", "a-panel-that-was-removed", "fans", "status"])
check("junk and duplicates are dropped",
      fresh.ordered()[:2], ["fans", "status"])
check("no panel appears twice",
      len(fresh.ordered()), len(set(fresh.ordered())))
check("every panel is still there",
      sorted(fresh.ordered()), sorted(DASHBOARD_PANELS))

fresh = reload_with("not a list")
check("a wrong type falls back to the default",
      fresh.ordered(), list(DASHBOARD_PANELS))

# -- what the dashboard actually packs -----------------------------------------

settings = Settings()
settings.dashboard_order = ["fans"] + [k for k in DASHBOARD_PANELS
                                       if k != "fans"]
settings.dashboard["fans"] = True
visible = [k for k in settings.ordered() if settings.visible(k)]
check("the packing order follows the setting", visible[0], "fans")

if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
