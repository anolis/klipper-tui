"""User settings persisted to disk."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Conservative, widely-applicable starting points. Override them per printer
# in the settings file rather than editing this list.
DEFAULT_PRESETS: dict[str, tuple[int, int]] = {
    "PLA": (200, 60),
    "PETG": (240, 80),
    "ABS": (240, 100),
    "TPU": (220, 50),
}

# Narrowest width in columns at which a panel is still worth looking at. The
# dashboard packs as many side by side as the terminal allows, so these decide
# both what pairs up and how a shared row is divided.
# These also weight the split: a row divides its width in proportion to them,
# so a panel needing half again as much as its neighbour gets it rather than an
# equal share it would overflow.
PANEL_MIN_WIDTH: dict[str, int] = {
    # Sized by their controls: these are rows of buttons and fields.
    "status": 58,
    "temperature": 57,
    "machine": 58,
    "fans": 56,
    "macros": 58,
    "objects": 60,
    "tuning": 68,
    "extruder": 68,
    "toolhead": 62,
    # Sized by what they draw. A heightmap, a chart or a camera frame squeezed
    # into a narrow column is legible but absurd, so these ask for room even
    # though their buttons would fit in half of it.
    "webcam": 80,
    "console": 72,
    "tempgraph": 78,
    "position": 80,
    "gcodeview": 80,
    "bedmesh": 74,
    "files": 96,
}

# key -> (label, default visible on the dashboard)
DASHBOARD_PANELS: dict[str, tuple[str, bool]] = {
    "status": ("Status", True),
    "temperature": ("Temperature", True),
    "tempgraph": ("Temperature History", True),
    "tuning": ("Speed & Flow", True),
    "machine": ("Motion Limits", True),
    "fans": ("Fans", True),
    "macros": ("Macros", True),
    "objects": ("Objects", False),
    "extruder": ("Extruder", True),
    "toolhead": ("Toolhead", False),
    "bedmesh": ("Bed Mesh", False),
    "position": ("Toolhead Position", False),
    "gcodeview": ("Toolpath", False),
    "webcam": ("Webcam", False),
    "console": ("Console", False),
    "files": ("G-code Files", False),
}


def state_path(name: str) -> Path:
    """Somewhere to keep regenerable data, kept out of the settings file."""
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state")
    return Path(base) / "klipper-tui" / name


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "klipper-tui" / "settings.json"


class Settings:
    def __init__(self) -> None:
        self.theme: str | None = None
        self.webcam_url: str | None = None
        self.presets: dict[str, tuple[int, int]] = dict(DEFAULT_PRESETS)
        self.filament_length: float = 100.0
        # Draw the temperature plot as a real image where the terminal can
        # show one. Off means braille everywhere, which is what a terminal
        # without graphics gets regardless.
        self.graph_hires: bool = True
        self.dashboard: dict[str, bool] = {
            k: default for k, (_, default) in DASHBOARD_PANELS.items()
        }
        self.load()

    def load(self) -> None:
        path = config_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if isinstance(data.get("theme"), str):
            self.theme = data["theme"]
        if isinstance(data.get("webcam_url"), str):
            self.webcam_url = data["webcam_url"].strip() or None
        presets = data.get("presets")
        if isinstance(presets, dict):
            parsed = {}
            for name, pair in presets.items():
                # Accept only [hotend, bed] pairs of sane numbers.
                if (isinstance(pair, list) and len(pair) == 2
                        and all(isinstance(v, (int, float)) for v in pair)):
                    parsed[str(name)] = (int(pair[0]), int(pair[1]))
            if parsed:
                self.presets = parsed
        length = data.get("filament_length")
        if isinstance(length, (int, float)) and length > 0:
            self.filament_length = float(length)
        if isinstance(data.get("graph_hires"), bool):
            self.graph_hires = data["graph_hires"]

        saved = data.get("dashboard")
        if isinstance(saved, dict):
            # Only accept known keys, so a stale file cannot inject panels.
            for key in DASHBOARD_PANELS:
                if isinstance(saved.get(key), bool):
                    self.dashboard[key] = saved[key]

    def save(self) -> None:
        path = config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(
                {
                    "theme": self.theme,
                    "webcam_url": self.webcam_url,
                    "presets": {k: list(v) for k, v in self.presets.items()},
                    "filament_length": self.filament_length,
                    "graph_hires": self.graph_hires,
                    "dashboard": self.dashboard,
                },
                indent=2,
            ))
        except OSError:
            pass

    def visible(self, key: str) -> bool:
        return self.dashboard.get(key, False)

    def toggle(self, key: str) -> bool:
        self.dashboard[key] = not self.dashboard.get(key, False)
        self.save()
        return self.dashboard[key]
