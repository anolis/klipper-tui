"""Motion limits: velocity, acceleration and the corner behaviour."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# key -> (toolhead field, label, unit, SET_VELOCITY_LIMIT parameter)
LIMITS = {
    "velocity": ("max_velocity", "Velocity", "mm/s", "VELOCITY"),
    "scv": ("square_corner_velocity", "Square corner velocity", "mm/s",
            "SQUARE_CORNER_VELOCITY"),
    "accel": ("max_accel", "Acceleration", "mm/s²", "ACCEL"),
    "cruise": ("minimum_cruise_ratio", "Min. cruise ratio", "%",
               "MINIMUM_CRUISE_RATIO"),
}


class MachinePanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="machine-panel", classes="panel")
        self.limit_defaults: dict = {}
        # Fields the user has touched. Live values must not overwrite an edit
        # in progress, and focus is not enough to tell: clicking Apply moves
        # focus away before the value is read.
        self.limits_edited: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Label("Motion limits", classes="panel-title")
        yield Static(
            "[$text-muted]Applied live, and lasting until the printer "
            "restarts. Reset returns them to printer.cfg.[/]"
        )
        for key, (_, label, unit, _) in LIMITS.items():
            with Horizontal(classes="btn-row"):
                yield Static(label, classes="limit-label")
                yield Input(id=f"mc-lim-{key}", classes="limit-input")
                yield Static(f"[$text-muted]{unit}[/]", classes="limit-unit")
        with Horizontal(classes="btn-row"):
            yield Button("Apply", id="mc-limits-apply", classes="-primary")
            yield Button("Reset", id="mc-limits-reset")
        yield Static("", id="mc-limits-note", classes="dim")

    # -- state -----------------------------------------------------------------

    def on_input_changed(self, event) -> None:
        widget_id = event.input.id or ""
        if widget_id.startswith("mc-lim-"):
            self.limits_edited.add(widget_id.removeprefix("mc-lim-"))

    def update_status(self, status: dict) -> None:
        """Show the live limits, leaving anything edited alone."""
        toolhead = status.get("toolhead") or {}
        settings = (status.get("configfile") or {}).get("settings") or {}
        self.limit_defaults = settings.get("printer") or {}

        for key, (field, _, _, _) in LIMITS.items():
            value = toolhead.get(field)
            if value is None:
                continue
            try:
                widget = self.query_one(f"#mc-lim-{key}", Input)
            except Exception:
                continue
            if key in self.limits_edited:
                continue
            formatted = self._format(key, value)
            if widget.value != formatted:
                widget.value = formatted
                # Assigning fires Input.Changed, which would otherwise look
                # like the user typing.
                self.limits_edited.discard(key)

    @staticmethod
    def _format(key: str, value: float) -> str:
        # Klipper carries the cruise ratio as 0-1; a percentage reads better,
        # and is how Mainsail shows it.
        if key == "cruise":
            return f"{value * 100:g}"
        return f"{value:g}"

    def note(self, message: str) -> None:
        try:
            self.query_one("#mc-limits-note", Static).update(message)
        except Exception:
            pass

    def clear_edits(self) -> None:
        self.limits_edited.clear()

    # -- values ----------------------------------------------------------------

    def read_limits(self) -> dict | None:
        """The edited limits as SET_VELOCITY_LIMIT parameters."""
        params: dict[str, float] = {}
        for key, (_, label, _, parameter) in LIMITS.items():
            try:
                raw = self.query_one(f"#mc-lim-{key}", Input).value.strip()
            except Exception:
                continue
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                self.note(f"[$error]{label} must be a number.[/]")
                return None
            if key == "cruise":
                if not 0 <= value < 100:
                    self.note("[$error]Min. cruise ratio must be 0 or more "
                              "and under 100%.[/]")
                    return None
                value /= 100.0
            elif value <= 0:
                self.note(f"[$error]{label} must be above zero.[/]")
                return None
            params[parameter] = value
        return params

    def default_limits(self) -> dict:
        params = {}
        for _, (field, _, _, parameter) in LIMITS.items():
            value = self.limit_defaults.get(field)
            if value is not None:
                params[parameter] = float(value)
        return params
