"""Toolhead panel: homing and jog controls."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Label, Static

STEP_SIZES = [0.1, 1.0, 10.0, 50.0]

# Babystepping nudges, in mm.
Z_NUDGES = [-0.05, -0.01, 0.01, 0.05]


class ToolheadPanel(Vertical):
    step = reactive(1.0)

    def __init__(self) -> None:
        super().__init__(id="toolhead-panel", classes="panel")
        self.z_offset = 0.0
        self.has_probe = False

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

        with Horizontal(classes="step-row compact-row"):
            yield Static("", id="th-step-label")
            for size in STEP_SIZES:
                yield Button(f"{size:g}mm", id=f"th-step-{size:g}".replace(".", "_"))

        with Horizontal(classes="btn-row"):
            yield Button("Motors Off", id="th-motors-off", classes="-danger")
            yield Button("Quad/Z Tilt", id="th-ztilt")

        yield Label("Z offset", classes="panel-title")
        yield Static("", id="th-zoffset")
        with Horizontal(classes="btn-row compact-row"):
            # Indexed ids: a widget id cannot contain "+" or ".".
            for index, nudge in enumerate(Z_NUDGES):
                yield Button(f"{nudge:+g}", id=f"th-znudge-{index}")
        with Horizontal(classes="btn-row compact-row"):
            yield Button("Reset", id="th-z-reset")
            yield Button("Save", id="th-z-save", classes="-success")

    def watch_step(self, value: float) -> None:
        try:
            self.query_one("#th-step-label", Static).update(
                f"[$text-muted]Step[/] [b $accent]{value:g}mm[/]  "
            )
        except Exception:
            pass

    def update_status(self, status: dict) -> None:
        move = status.get("gcode_move") or {}
        origin = move.get("homing_origin") or [0, 0, 0, 0]
        self.z_offset = float(origin[2]) if len(origin) > 2 else 0.0

        settings = (status.get("configfile") or {}).get("settings") or {}
        # Whichever of these is configured decides how the offset is saved.
        self.has_probe = any(
            name in settings
            for name in ("probe", "bltouch", "smart_effector",
                         "probe_eddy_current")
        )
        saved = None
        for name in ("bltouch", "probe", "smart_effector"):
            section = settings.get(name)
            if section and section.get("z_offset") is not None:
                saved = float(section["z_offset"])
                break

        colour = "$foreground" if abs(self.z_offset) < 1e-9 else "$warning"
        stored = f"   [$text-muted]probe z_offset[/] {saved:.3f}" \
            if saved is not None else ""
        self.query_one("#th-zoffset", Static).update(
            f"[$text-muted]live offset[/] [{colour} b]{self.z_offset:+.3f}[/]mm"
            f"{stored}"
        )

    def z_apply_command(self) -> str:
        """Fold the live offset into the saved one."""
        return ("Z_OFFSET_APPLY_PROBE" if getattr(self, "has_probe", False)
                else "Z_OFFSET_APPLY_ENDSTOP")

    def jog_gcode(self, axis: str, direction: int) -> str:
        # Relative move, then restore absolute mode. G91/G90 are wrapped here
        # deliberately: an aborted relative-mode jog previously left the printer
        # stuck in G91 and broke the next print.
        dist = self.step * direction
        return f"G91\nG1 {axis}{dist:g} F3000\nG90"
