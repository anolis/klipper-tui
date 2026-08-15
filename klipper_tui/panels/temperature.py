"""Temperature panel: live heater readouts, manual targets, and presets."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# name -> (extruder target, bed target)
PRESETS: dict[str, tuple[int, int]] = {
    "PLA": (200, 60),
    "PETG": (240, 80),
    "ABS": (250, 100),
    "TPU": (225, 50),
}


class TemperaturePanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="temp-panel", classes="panel")

    def compose(self) -> ComposeResult:
        yield Label("Temperature", classes="panel-title")
        yield Static("", id="tp-extruder")
        yield Static("", id="tp-bed")
        yield Static("", id="tp-fan")

        with Horizontal(classes="btn-row"):
            yield Input(placeholder="hotend °C", id="tp-in-ext", type="integer")
            yield Input(placeholder="bed °C", id="tp-in-bed", type="integer")
            yield Button("Set", id="tp-set", classes="-primary")

        with Horizontal(classes="btn-row"):
            for name in PRESETS:
                yield Button(name, id=f"tp-preset-{name}")
            yield Button("Cool", id="tp-cooldown", classes="-danger")

    def update_status(self, status: dict) -> None:
        ext = status.get("extruder", {})
        bed = status.get("heater_bed", {})
        fan = status.get("fan", {})

        self.query_one("#tp-extruder", Static).update(
            self._heater_line("Hotend", ext)
        )
        self.query_one("#tp-bed", Static).update(self._heater_line("Bed", bed))

        speed = (fan.get("speed") or 0) * 100
        self.query_one("#tp-fan", Static).update(
            f"[#9e9e9e]Part fan[/] [b]{speed:.0f}%[/b]"
        )

    def _heater_line(self, label: str, obj: dict) -> str:
        current = obj.get("temperature")
        target = obj.get("target") or 0
        power = (obj.get("power") or 0) * 100
        cur = f"{current:.1f}" if current is not None else "--"

        if target:
            # Colour by how far the heater still has to climb.
            delta = abs((current or 0) - target)
            color = "#4caf50" if delta < 2 else "#ff9800"
            tgt = f"[{color}]{target:.0f}°C[/]"
        else:
            tgt = "[#9e9e9e]off[/]"

        return (
            f"[#9e9e9e]{label:<8}[/][b]{cur}[/b]°C [#9e9e9e]/[/] {tgt}"
            f"   [#9e9e9e]power[/] {power:.0f}%"
        )
