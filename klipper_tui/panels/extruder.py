"""Extruder panel: jog extrusion, load/unload filament, retraction settings."""

from __future__ import annotations

import math

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# Klipper refuses to extrude below min_extrude_temp (default 170C).
MIN_EXTRUDE_TEMP = 170

# A direct-drive-safe default; bowden printers should raise it in settings.
# The printer's own max_extrude_only_distance still caps any single move, so
# long runs are split into chunks.
DEFAULT_LOAD_LENGTH = 100
DEFAULT_FAST = 50      # mm/s through the bowden
DEFAULT_SLOW = 5       # mm/s through the melt zone
MELT_ZONE = 60         # final mm of a load fed slowly


class ExtruderPanel(Vertical):
    def __init__(self, load_length: float = DEFAULT_LOAD_LENGTH) -> None:
        super().__init__(id="extruder-panel", classes="panel")
        self.max_extrude_only = 50.0
        self.load_length = load_length

    def compose(self) -> ComposeResult:
        yield Label("Extruder", classes="panel-title")
        yield Static("", id="ex-temp")

        with Horizontal(classes="btn-row"):
            yield Input(value="25", id="ex-amount", type="number")
            yield Input(value="5", id="ex-feedrate", type="number")
            yield Button("Extrude", id="ex-extrude", classes="-primary")
            yield Button("Retract", id="ex-retract")
        yield Static("[$text-muted]amount (mm) / feedrate (mm/s)[/]")

        yield Label("Filament", classes="panel-title")
        with Horizontal(classes="btn-row"):
            yield Input(value=f"{self.load_length:g}", id="ex-fil-len",
                        type="number")
            yield Input(value=str(DEFAULT_FAST), id="ex-fil-speed",
                        type="number")
            yield Button("Load", id="ex-load", classes="-success")
            yield Button("Unload", id="ex-unload", classes="-danger")
        yield Static("", id="ex-fil-hint")

        yield Label("Firmware retraction", classes="panel-title")
        with Horizontal(classes="btn-row"):
            yield Input(placeholder="retract len", id="ex-rt-len", type="number")
            yield Input(placeholder="retract speed", id="ex-rt-speed",
                        type="number")
            yield Button("Apply", id="ex-rt-apply", classes="-primary")
        yield Static("", id="ex-rt-current")

    def on_mount(self) -> None:
        self.query_one("#ex-fil-hint", Static).update(
            f"[$text-muted]length (mm) / speed (mm/s) — last {MELT_ZONE}mm of a "
            f"load is fed at {DEFAULT_SLOW}mm/s through the nozzle[/]"
        )

    def update_status(self, status: dict) -> None:
        ext = status.get("extruder", {})
        current = ext.get("temperature")
        target = ext.get("target") or 0
        cur_txt = f"{current:.1f}" if current is not None else "--"

        if current is not None and current < MIN_EXTRUDE_TEMP:
            warn = f"  [$warning]cold — min {MIN_EXTRUDE_TEMP}°C to extrude[/]"
        else:
            warn = "  [$success]ready[/]"

        self.query_one("#ex-temp", Static).update(
            f"[$text-muted]Hotend[/] [b]{cur_txt}[/b]°C "
            f"[$text-muted]/ {target:.0f}°C[/]{warn}"
        )

        cfg = (status.get("configfile") or {}).get("config") or {}
        limit = (cfg.get("extruder") or {}).get("max_extrude_only_distance")
        if limit:
            self.max_extrude_only = float(limit)

        fr = status.get("firmware_retraction", {})
        if fr:
            self.query_one("#ex-rt-current", Static).update(
                f"[$text-muted]current:[/] len [b]{fr.get('retract_length', 0):g}mm[/b]  "
                f"speed [b]{fr.get('retract_speed', 0):g}mm/s[/b]  "
                f"unretract extra [b]{fr.get('unretract_extra_length', 0):g}mm[/b]"
            )

    def can_extrude(self, status: dict) -> bool:
        current = status.get("extruder", {}).get("temperature")
        return current is not None and current >= MIN_EXTRUDE_TEMP

    # -- gcode builders --------------------------------------------------------

    def _chunks(self, total: float) -> list[float]:
        """Split a long extrude into equal moves within the printer's limit.

        Splitting evenly rather than greedily avoids a useless 1mm remainder
        when the total sits just above the limit.
        """
        total = abs(total)
        if total <= 0:
            return []
        limit = max(1.0, self.max_extrude_only - 1.0)
        count = math.ceil(total / limit)
        return [total / count] * count

    def move_gcode(self, amount: float, feedrate: float, direction: int) -> str:
        # M83 sets relative extrusion; restore M82 afterwards so a later print
        # that assumes absolute extrusion is not silently broken.
        lines = ["M83"]
        for step in self._chunks(amount):
            lines.append(f"G1 E{step * direction:g} F{feedrate * 60:g}")
        lines.append("M82")
        return "\n".join(lines)

    def load_gcode(self, length: float, fast: float) -> str:
        """Feed quickly down the bowden, then slowly through the melt zone."""
        bulk = max(0.0, length - MELT_ZONE)
        melt = min(length, MELT_ZONE)
        lines = ["M83"]
        for step in self._chunks(bulk):
            lines.append(f"G1 E{step:g} F{fast * 60:g}")
        for step in self._chunks(melt):
            lines.append(f"G1 E{step:g} F{DEFAULT_SLOW * 60:g}")
        lines.append("M82")
        return "\n".join(lines)

    def unload_gcode(self, length: float, fast: float) -> str:
        """Purge briefly to soften the tip, then pull the filament out."""
        lines = ["M83", f"G1 E10 F{DEFAULT_SLOW * 60:g}"]
        for step in self._chunks(length):
            lines.append(f"G1 E-{step:g} F{fast * 60:g}")
        lines.append("M82")
        return "\n".join(lines)
