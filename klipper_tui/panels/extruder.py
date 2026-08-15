"""Extruder panel: extrude/retract, load/unload, retraction settings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# Klipper refuses to extrude below min_extrude_temp (default 170C).
MIN_EXTRUDE_TEMP = 170


class ExtruderPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="extruder-panel", classes="panel")

    def compose(self) -> ComposeResult:
        yield Label("Extruder", classes="panel-title")
        yield Static("", id="ex-temp")

        with Horizontal(classes="btn-row"):
            yield Input(value="25", id="ex-amount", type="number")
            yield Input(value="5", id="ex-feedrate", type="number")
            yield Button("Extrude", id="ex-extrude", classes="-primary")
            yield Button("Retract", id="ex-retract")

        yield Static(
            "[#9e9e9e]amount (mm) / feedrate (mm/s)[/]", classes="dim"
        )

        with Horizontal(classes="btn-row"):
            yield Button("Load Filament", id="ex-load", classes="-success")
            yield Button("Unload Filament", id="ex-unload", classes="-danger")

        yield Label("Firmware retraction", classes="panel-title")
        with Horizontal(classes="btn-row"):
            yield Input(placeholder="retract len", id="ex-rt-len", type="number")
            yield Input(placeholder="retract speed", id="ex-rt-speed", type="number")
            yield Button("Apply", id="ex-rt-apply", classes="-primary")
        yield Static("", id="ex-rt-current")

    def update_status(self, status: dict) -> None:
        ext = status.get("extruder", {})
        current = ext.get("temperature")
        target = ext.get("target") or 0
        cur_txt = f"{current:.1f}" if current is not None else "--"

        if current is not None and current < MIN_EXTRUDE_TEMP:
            warn = f"  [#ff9800]cold — min {MIN_EXTRUDE_TEMP}°C to extrude[/]"
        else:
            warn = "  [#4caf50]ready[/]"

        self.query_one("#ex-temp", Static).update(
            f"[#9e9e9e]Hotend[/] [b]{cur_txt}[/b]°C "
            f"[#9e9e9e]/ {target:.0f}°C[/]{warn}"
        )

        fr = status.get("firmware_retraction", {})
        if fr:
            self.query_one("#ex-rt-current", Static).update(
                f"[#9e9e9e]current:[/] len [b]{fr.get('retract_length', 0):g}mm[/b]  "
                f"speed [b]{fr.get('retract_speed', 0):g}mm/s[/b]  "
                f"unretract extra [b]{fr.get('unretract_extra_length', 0):g}mm[/b]"
            )

    def can_extrude(self, status: dict) -> bool:
        current = status.get("extruder", {}).get("temperature")
        return current is not None and current >= MIN_EXTRUDE_TEMP

    def move_gcode(self, amount: float, feedrate: float, direction: int) -> str:
        # M83 sets relative extrusion; restore M82 afterwards so a later print
        # that assumes absolute extrusion is not silently broken.
        dist = amount * direction
        return f"M83\nG1 E{dist:g} F{feedrate * 60:g}\nM82"
