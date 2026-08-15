"""User settings persisted to disk."""

from __future__ import annotations

import json
import os
from pathlib import Path

# key -> (label, default visible on the dashboard)
DASHBOARD_PANELS: dict[str, tuple[str, bool]] = {
    "status": ("Status", True),
    "temperature": ("Temperature", True),
    "tempgraph": ("Temperature History", True),
    "tuning": ("Speed & Flow", True),
    "extruder": ("Extruder", True),
    "toolhead": ("Toolhead", False),
    "bedmesh": ("Bed Mesh", False),
    "position": ("Toolhead Position", False),
    "webcam": ("Webcam", False),
    "console": ("Console", False),
    "files": ("G-code Files", False),
}


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "klipper-tui" / "settings.json"


class Settings:
    def __init__(self) -> None:
        self.theme: str | None = None
        self.webcam_url: str | None = None
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
