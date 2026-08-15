"""Temperature panel: live heater readouts, manual targets, and presets."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

from ..settings import DEFAULT_PRESETS

# Overridden from the settings file at start-up; see set_presets().
PRESETS: dict[str, tuple[int, int]] = dict(DEFAULT_PRESETS)


def set_presets(presets: dict[str, tuple[int, int]]) -> None:
    """Replace the presets in place, so importers see the update."""
    PRESETS.clear()
    PRESETS.update(presets)


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

        with Horizontal(classes="btn-row compact-row"):
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
            f"[$text-muted]Part fan[/] [b]{speed:.0f}%[/b]"
        )

    def _heater_line(self, label: str, obj: dict) -> str:
        current = obj.get("temperature")
        target = obj.get("target") or 0
        power = (obj.get("power") or 0) * 100
        cur = f"{current:.1f}" if current is not None else "--"

        if target:
            # Colour by how far the heater still has to climb.
            delta = abs((current or 0) - target)
            color = "$success" if delta < 2 else "$warning"
            tgt = f"[{color}]{target:.0f}°C[/]"
        else:
            tgt = "[$text-muted]off[/]"

        return (
            f"[$text-muted]{label:<8}[/][b]{cur}[/b]°C [$text-muted]/[/] {tgt}"
            f"   [$text-muted]power[/] {power:.0f}%"
        )
