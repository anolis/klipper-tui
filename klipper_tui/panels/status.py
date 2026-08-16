"""Status panel: printer state, current job, progress, position."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from datetime import datetime, timedelta

from ..format import duration, state_markup


class StatusPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="status-panel", classes="panel")
        # Slicer metadata for the running job, once the app has fetched it.
        # Status updates arrive before that and read this, so it cannot wait
        # for set_job_metadata to create it.
        self.job_meta: dict = {}

    def compose(self) -> ComposeResult:
        yield Label("Status", classes="panel-title")
        yield Static("", id="st-state")
        yield Static("", id="st-file")
        yield Static("", id="st-progress")
        yield Static("", id="st-times")
        yield Static("", id="st-pos")
        yield Static("", id="st-homed")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("Pause", id="st-pause")
            yield Button("Resume", id="st-resume", classes="-success")
            yield Button("Cancel", id="st-cancel", classes="-danger")
            yield Button("Restart", id="st-restart", classes="-primary")

    @staticmethod
    def _progress_bar(percent: float, state: str) -> str:
        """A filled bar, matching the fan and speed bars elsewhere."""
        width = 34
        filled = max(0, min(width, int(round(percent / 100 * width))))
        colour = {
            "printing": "$accent",
            "paused": "$warning",
            "complete": "$success",
            "cancelled": "$error",
            "error": "$error",
        }.get(state.lower(), "$text-muted")
        return (f"[{colour}]{'█' * filled}[/]"
                f"[$panel-lighten-2]{'░' * (width - filled)}[/] "
                f"[b]{percent:5.1f}%[/b]")

    def set_job_metadata(self, meta: dict) -> None:
        self.job_meta = meta or {}

    def _remaining(self, stats: dict, sd: dict, elapsed: float,
                   progress: float) -> tuple[float, str]:
        """Time left, and where the figure came from.

        The slicer's own estimate is used when Moonraker has it: extrapolating
        from file position is wildly wrong early in a print, which is exactly
        when an ETA is most wanted. Filament used is the next best signal, and
        file position the last resort.
        """
        slicer = self.job_meta.get("estimated_time")
        if slicer and slicer > 0:
            return max(0.0, slicer - elapsed), "slicer"

        used = stats.get("filament_used") or 0
        total = self.job_meta.get("filament_total") or 0
        if used > 0 and total > 0 and used < total:
            return elapsed * (total / used - 1), "filament"

        # Only meaningful once enough of the file has been read.
        if progress > 2:
            return max(0.0, elapsed * (100 / progress - 1)), "file"
        return 0.0, ""

    def _set_job_buttons(self, state: str, has_file: bool) -> None:
        """Only offer what the current job state actually allows."""
        printing = state == "printing"
        paused = state == "paused"
        enabled = {
            "st-pause": printing,
            "st-resume": paused,
            "st-cancel": printing or paused,
            # Restarting needs a file to go back to, but the job itself may
            # already have stopped.
            "st-restart": has_file,
        }
        for widget_id, on in enabled.items():
            try:
                self.query_one(f"#{widget_id}", Button).disabled = not on
            except Exception:
                pass

    def update_status(self, status: dict, klippy_state: str) -> None:
        stats = status.get("print_stats", {})
        sd = status.get("virtual_sdcard", {})
        toolhead = status.get("toolhead", {})
        gcode_move = status.get("gcode_move", {})

        state = stats.get("state") or klippy_state
        self._set_job_buttons(state, bool(stats.get("filename")))
        self.query_one("#st-state", Static).update(
            f"State  {state_markup(state)}"
        )

        filename = stats.get("filename") or ""
        self.query_one("#st-file", Static).update(
            f"[$text-muted]File[/]   {filename or '[$text-muted]none[/]'}"
        )

        progress = (sd.get("progress") or 0.0) * 100
        self.query_one("#st-progress", Static).update(
            self._progress_bar(progress, state)
        )

        elapsed = stats.get("print_duration") or 0
        remaining, source = self._remaining(stats, sd, elapsed, progress)
        finish = ""
        if remaining:
            done_at = datetime.now() + timedelta(seconds=remaining)
            finish = f"[$text-muted] ({done_at.strftime('%H:%M')})[/]"
        self.query_one("#st-times", Static).update(
            f"[$text-muted]Elapsed[/] {duration(elapsed)}   "
            f"[$text-muted]ETA[/] {duration(remaining)}{finish}"
            f"[$text-muted]{' ' + source if source else ''}[/]   "
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
