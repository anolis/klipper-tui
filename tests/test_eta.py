"""Where the remaining-time figure comes from.

Extrapolating from file position is badly wrong early in a print, which is
exactly when an ETA matters, so the slicer's own estimate is preferred.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.status import StatusPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


panel = StatusPanel.__new__(StatusPanel)


def remaining(meta, elapsed, progress, filament_used=0.0):
    panel.job_meta = meta
    return panel._remaining(
        {"filament_used": filament_used}, {}, elapsed, progress)


# A real case: 6h28m job, 41 minutes in, barely 1% of the file read.
value, source = remaining({"estimated_time": 23272}, 2455, 1.05)
check("slicer estimate is used", source == "slicer", source)
check("slicer figure is right", abs(value - (23272 - 2455)) < 1, value)
check("elapsed plus remaining equals the estimate",
      abs((2455 + value) - 23272) < 1)

# Without a slicer figure, filament used tracks better than file position.
value, source = remaining({"filament_total": 100.0}, 600, 1.0,
                          filament_used=25.0)
check("falls back to filament", source == "filament", source)
check("filament figure is right", abs(value - 1800) < 1, value)

# With neither, file position is the last resort, and only once it means
# something.
value, source = remaining({}, 600, 25.0)
check("falls back to file", source == "file", source)
check("file figure is right", abs(value - 1800) < 1, value)

value, source = remaining({}, 600, 0.9)
check("no guess from under 2% of the file", source == "" and value == 0,
      f"{value} {source}")

# A finished or overrunning job must not report negative time.
value, _ = remaining({"estimated_time": 100}, 500, 99.0)
check("never negative", value == 0, value)

# Bad metadata must not be trusted.
for meta in ({"estimated_time": 0}, {"estimated_time": None},
             {"filament_total": 0}):
    _, source = remaining(meta, 600, 0.5)
    check(f"ignores {meta}", source == "", source)

for f in failures:
    print("FAIL", f)
print("eta: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
