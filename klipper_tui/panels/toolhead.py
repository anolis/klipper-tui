"""Toolhead panel: homing and jog controls."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Label, Static

STEP_SIZES = [0.1, 1.0, 10.0, 50.0]


class ToolheadPanel(Vertical):
    step = reactive(1.0)

    def __init__(self) -> None:
        super().__init__(id="toolhead-panel", classes="panel")

    def compose(self) -> ComposeResult:
        yield Label("Toolhead", classes="panel-title")

        with Horizontal(classes="btn-row"):
            yield Button("Home All", id="th-home-all", classes="-primary")
            yield Button("Home X", id="th-home-x")
            yield Button("Home Y", id="th-home-y")
            yield Button("Home Z", id="th-home-z")

        with Horizontal(classes="btn-row"):
            yield Button("X-", id="th-x-neg")
            yield Button("X+", id="th-x-pos")
            yield Button("Y-", id="th-y-neg")
            yield Button("Y+", id="th-y-pos")
            yield Button("Z-", id="th-z-neg")
            yield Button("Z+", id="th-z-pos")

        with Horizontal(classes="step-row"):
            yield Static("", id="th-step-label")
            for size in STEP_SIZES:
                yield Button(f"{size:g}mm", id=f"th-step-{size:g}".replace(".", "_"))

        with Horizontal(classes="btn-row"):
            yield Button("Motors Off", id="th-motors-off", classes="-danger")
            yield Button("Quad/Z Tilt", id="th-ztilt")

    def watch_step(self, value: float) -> None:
        try:
            self.query_one("#th-step-label", Static).update(
                f"[#9e9e9e]Step[/] [b #2196f3]{value:g}mm[/]  "
            )
        except Exception:
            pass

    def jog_gcode(self, axis: str, direction: int) -> str:
        # Relative move, then restore absolute mode. G91/G90 are wrapped here
        # deliberately: an aborted relative-mode jog previously left the printer
        # stuck in G91 and broke the next print.
        dist = self.step * direction
        return f"G91\nG1 {axis}{dist:g} F3000\nG90"
