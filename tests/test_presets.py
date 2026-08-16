"""Validation for the preset editor."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.settings import SettingsPanel

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


class Field:
    def __init__(self, value=""):
        self.value = value


class Panel(SettingsPanel):
    """Stands in for the mounted widget tree."""

    def __init__(self, rows, new=("", "", "")):
        self.preset_order = [r[0] for r in rows]
        self.fields = {}
        for index, (name, hot, bed) in enumerate(rows):
            self.fields[f"#st-pn-{index}"] = Field(name)
            self.fields[f"#st-ph-{index}"] = Field(hot)
            self.fields[f"#st-pb-{index}"] = Field(bed)
        self.fields["#st-preset-new-name"] = Field(new[0])
        self.fields["#st-preset-new-hot"] = Field(new[1])
        self.fields["#st-preset-new-bed"] = Field(new[2])
        self.notes = []
        self.settings = type("S", (), {"presets": {r[0]: (0, 0) for r in rows}})()

    def query_one(self, selector, *args):
        return self.fields[selector]

    def _note(self, message):
        self.notes.append(message)


good = Panel([("PLA", "215", "65"), ("PETG", "260", "80")])
check("reads edited rows",
      good.read_presets() == {"PLA": (215, 65), "PETG": (260, 80)},
      f"{good.read_presets()}")

blank = Panel([("", "215", "65")])
check("rejects a nameless preset", blank.read_presets() is None)
check("says why", any("name" in n for n in blank.notes), blank.notes)

bad = Panel([("PLA", "hot", "65")])
check("rejects a non-numeric temperature", bad.read_presets() is None)

dupe = Panel([("PLA", "215", "65"), ("PLA", "200", "60")])
check("rejects duplicate names", dupe.read_presets() is None)
check("names the clash", any("PLA" in n for n in dupe.notes), dupe.notes)

# Adding
adding = Panel([("PLA", "215", "65")], new=("TPU", "250", "80"))
check("accepts a new preset", adding.new_preset() == ("TPU", (250, 80)),
      f"{adding.new_preset()}")

unnamed = Panel([("PLA", "215", "65")], new=("", "250", "80"))
check("new preset needs a name", unnamed.new_preset() is None)

existing = Panel([("PLA", "215", "65")], new=("PLA", "250", "80"))
check("will not add a duplicate", existing.new_preset() is None)

# A bed temperature is optional; not every material wants one.
nobed = Panel([("PLA", "215", "65")], new=("PC", "270", ""))
check("bed may be left blank", nobed.new_preset() == ("PC", (270, 0)),
      f"{nobed.new_preset()}")

check("row lookup by position", good.preset_at(1) == "PETG")
check("out of range is safe", good.preset_at(9) is None)

for f in failures:
    print("FAIL", f)
print("presets: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
