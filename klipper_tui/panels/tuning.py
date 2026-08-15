"""Live speed and flow multipliers (M220 / M221)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# name -> (label, gcode command, presets)
FACTORS = {
    "speed": ("Speed", "M220", [50, 75, 100, 125, 150, 200]),
    "flow": ("Flow", "M221", [90, 95, 100, 105, 110]),
}

BAR_WIDTH = 40
BAR_MAX = 200.0


class TuningPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="tuning-panel", classes="panel")
        self.values = {"speed": 100.0, "flow": 100.0}

    def compose(self) -> ComposeResult:
        yield Label("Speed & Flow", classes="panel-title")

        for key, (label, _, presets) in FACTORS.items():
            yield Static("", id=f"tn-{key}-bar")
            with Horizontal(classes="btn-row compact-row"):
                yield Button("−5", id=f"tn-{key}-down")
                yield Button("+5", id=f"tn-{key}-up")
                for p in presets:
                    yield Button(f"{p}%", id=f"tn-{key}-set-{p}")
                yield Input(placeholder=f"{label} %", id=f"tn-{key}-input",
                            type="integer")

    def update_status(self, status: dict) -> None:
        gm = status.get("gcode_move") or {}
        self.values["speed"] = (gm.get("speed_factor") or 1.0) * 100
        self.values["flow"] = (gm.get("extrude_factor") or 1.0) * 100
        self._redraw()

    def _redraw(self) -> None:
        for key, (label, _, _) in FACTORS.items():
            value = self.values[key]
            filled = int(min(1.0, value / BAR_MAX) * BAR_WIDTH)
            # Colour by distance from 100%, so an unusual setting stands out.
            if abs(value - 100) < 0.5:
                color = "$success"
            elif abs(value - 100) <= 25:
                color = "$accent"
            else:
                color = "$warning"
            bar = f"[{color}]{'█' * filled}[/][$panel-lighten-2]{'░' * (BAR_WIDTH - filled)}[/]"
            try:
                self.query_one(f"#tn-{key}-bar", Static).update(
                    f"[$text-muted]{label:<6}[/]{bar} [b]{value:5.0f}%[/b]"
                )
            except Exception:
                pass

    def command_for(self, key: str, value: float) -> str:
        _, cmd, _ = FACTORS[key]
        return f"{cmd} S{value:.0f}"

    def nudge(self, key: str, delta: float) -> float:
        return max(10.0, min(300.0, self.values[key] + delta))
