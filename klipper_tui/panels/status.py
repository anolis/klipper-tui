"""Status panel: printer state, current job, progress, position."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, ProgressBar, Static

from ..format import duration, state_markup


class StatusPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="status-panel", classes="panel")

    def compose(self) -> ComposeResult:
        yield Label("Status", classes="panel-title")
        yield Static("", id="st-state")
        yield Static("", id="st-file")
        yield ProgressBar(total=100, show_eta=False, id="st-progress")
        yield Static("", id="st-times")
        yield Static("", id="st-pos")
        yield Static("", id="st-homed")

    def update_status(self, status: dict, klippy_state: str) -> None:
        stats = status.get("print_stats", {})
        sd = status.get("virtual_sdcard", {})
        toolhead = status.get("toolhead", {})
        gcode_move = status.get("gcode_move", {})

        state = stats.get("state") or klippy_state
        self.query_one("#st-state", Static).update(
            f"State  {state_markup(state)}"
        )

        filename = stats.get("filename") or ""
        self.query_one("#st-file", Static).update(
            f"[$text-muted]File[/]   {filename or '[$text-muted]none[/]'}"
        )

        progress = (sd.get("progress") or 0.0) * 100
        self.query_one("#st-progress", ProgressBar).update(progress=progress)

        elapsed = stats.get("print_duration") or 0
        total_est = (elapsed / (progress / 100)) if progress > 1 else 0
        remaining = max(0, total_est - elapsed) if total_est else 0
        self.query_one("#st-times", Static).update(
            f"[$text-muted]Elapsed[/] {duration(elapsed)}   "
            f"[$text-muted]ETA[/] {duration(remaining)}   "
            f"[$text-muted]{progress:.1f}%[/]"
        )

        pos = gcode_move.get("gcode_position") or toolhead.get("position") or []
        if len(pos) >= 3:
            self.query_one("#st-pos", Static).update(
                f"[$text-muted]Pos[/]    X [b]{pos[0]:.2f}[/b]  "
                f"Y [b]{pos[1]:.2f}[/b]  Z [b]{pos[2]:.3f}[/b]"
            )

        homed = toolhead.get("homed_axes", "")
        marks = " ".join(
            f"[$success]{ax.upper()}[/]" if ax in homed else f"[$error]{ax.upper()}[/]"
            for ax in "xyz"
        )
        speed = (gcode_move.get("speed_factor") or 1) * 100
        flow = (gcode_move.get("extrude_factor") or 1) * 100
        self.query_one("#st-homed", Static).update(
            f"[$text-muted]Homed[/]  {marks}   "
            f"[$text-muted]Speed[/] {speed:.0f}%   [$text-muted]Flow[/] {flow:.0f}%"
        )
