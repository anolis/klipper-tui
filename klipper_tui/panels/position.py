"""A deliberately lo-fi 3D toolhead position display, LCARS-flavoured.

The build volume is drawn as a rotating wireframe in braille cells, with the
toolhead marked and dropped to the bed so its footprint is readable.
"""

from __future__ import annotations

import math

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from ..braille import BrailleCanvas

# LCARS-ish palette: warm amber structure, lavender accents, hot marker.
C_FRAME = "#ff9966"
C_FLOOR = "#9999cc"
C_HEAD = "#ffcc00"
C_DROP = "#cc6666"
C_AXIS = "#99ccff"

# Cube corners as unit coordinates, and the 12 edges joining them.
CORNERS = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
]
EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # floor
    (4, 5), (5, 6), (6, 7), (7, 4),  # ceiling
    (0, 4), (1, 5), (2, 6), (3, 7),  # verticals
]


class PositionPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="position-panel")
        self.yaw = 0.6
        self.tilt = 0.5
        self.spinning = True
        self.pos = [0.0, 0.0, 0.0]
        self.limits = ([0.0, 0.0, 0.0], [245.0, 260.0, 400.0])
        self.homed = ""

    def compose(self) -> ComposeResult:
        yield Label("Toolhead Position", classes="panel-title")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("◄", id="ps-left")
            yield Button("►", id="ps-right")
            yield Button("▲", id="ps-up")
            yield Button("▼", id="ps-down")
            yield Button("Spin", id="ps-spin", classes="-primary")

        yield Static("", id="ps-readout")
        yield Static("", id="ps-view", markup=True)

    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        if self.spinning:
            self.yaw = (self.yaw + 0.03) % (2 * math.pi)
        self._redraw()

    # -- data ------------------------------------------------------------------

    def update_status(self, status: dict) -> None:
        toolhead = status.get("toolhead") or {}
        gcode_move = status.get("gcode_move") or {}
        pos = gcode_move.get("gcode_position") or toolhead.get("position")
        if pos and len(pos) >= 3:
            self.pos = [float(pos[0]), float(pos[1]), float(pos[2])]
        lo = toolhead.get("axis_minimum")
        hi = toolhead.get("axis_maximum")
        if lo and hi:
            self.limits = ([float(v) for v in lo[:3]],
                           [float(v) for v in hi[:3]])
        self.homed = toolhead.get("homed_axes", "")

    def rotate(self, dyaw: float = 0.0, dtilt: float = 0.0) -> None:
        self.yaw = (self.yaw + dyaw) % (2 * math.pi)
        self.tilt = max(-1.4, min(1.4, self.tilt + dtilt))
        self._redraw()

    def toggle_spin(self) -> bool:
        self.spinning = not self.spinning
        return self.spinning

    # -- projection ------------------------------------------------------------

    def _aspect(self) -> tuple[float, float, float]:
        """Volume proportions, largest axis normalised to 1."""
        lo, hi = self.limits
        dims = [max(1.0, hi[i] - lo[i]) for i in range(3)]
        longest = max(dims)
        return tuple(d / longest for d in dims)  # type: ignore[return-value]

    def _raw(self, u: float, v: float, w: float) -> tuple[float, float]:
        """Unit coords -> unscaled projected plane coords."""
        ax, ay, az = self._aspect()
        x = (u - 0.5) * ax
        y = (v - 0.5) * ay
        z = (w - 0.5) * az

        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        rx = x * cos_y - y * sin_y
        ry = x * sin_y + y * cos_y

        cos_t, sin_t = math.cos(self.tilt), math.sin(self.tilt)
        return (rx, ry * sin_t - z * cos_t)

    def _fit(self, cw: int, ch: int) -> tuple[float, float, float]:
        """Scale and offsets that fit the whole volume at this rotation."""
        pts = [self._raw(*c) for c in CORNERS]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_x = max(xs) - min(xs) or 1.0
        span_y = max(ys) - min(ys) or 1.0
        scale = min(cw / span_x, ch / span_y) * 0.88
        off_x = cw / 2 - (max(xs) + min(xs)) / 2 * scale
        off_y = ch / 2 - (max(ys) + min(ys)) / 2 * scale
        return scale, off_x, off_y

    def _project(self, u: float, v: float, w: float,
                 fit: tuple[float, float, float]) -> tuple[int, int]:
        scale, off_x, off_y = fit
        rx, ry = self._raw(u, v, w)
        return (int(off_x + rx * scale), int(off_y + ry * scale))

    # -- drawing ---------------------------------------------------------------

    def _redraw(self) -> None:
        try:
            view = self.query_one("#ps-view", Static)
            readout = self.query_one("#ps-readout", Static)
        except Exception:
            return

        width = max(20, (view.size.width or self.size.width) - 2)
        height = max(8, (view.size.height or 16) - 1)
        canvas = BrailleCanvas(width, height)
        cw, ch = canvas.sub_width, canvas.sub_height

        fit = self._fit(cw, ch)
        pts = [self._project(*c, fit) for c in CORNERS]
        floor_edges = set(EDGES[:4])
        for a, b in EDGES:
            # Floor edges get the cooler colour so the base plane reads clearly.
            color = C_FLOOR if (a, b) in floor_edges else C_FRAME
            canvas.line(*pts[a], *pts[b], color)

        # Floor grid, quartered each way.
        for i in (1, 2, 3):
            f = i / 4
            canvas.line(*self._project(f, 0, 0, fit),
                        *self._project(f, 1, 0, fit), C_FLOOR)
            canvas.line(*self._project(0, f, 0, fit),
                        *self._project(1, f, 0, fit), C_FLOOR)

        lo, hi = self.limits
        u, v, w = (self._norm(self.pos[i], lo[i], hi[i]) for i in range(3))

        # Drop line from the toolhead to the bed, plus a floor crosshair.
        head = self._project(u, v, w, fit)
        foot = self._project(u, v, 0, fit)
        canvas.line(*foot, *head, C_DROP)
        canvas.line(*self._project(0, v, 0, fit),
                    *self._project(1, v, 0, fit), C_DROP)
        canvas.line(*self._project(u, 0, 0, fit),
                    *self._project(u, 1, 0, fit), C_DROP)

        # Toolhead marker, drawn last so it wins any shared cell.
        for dx in range(-2, 3):
            canvas.set(head[0] + dx, head[1], C_HEAD)
        for dy in range(-2, 3):
            canvas.set(head[0], head[1] + dy, C_HEAD)

        view.update("\n".join(canvas.render()))

        homed = " ".join(
            f"[#4caf50]{a.upper()}[/]" if a in self.homed
            else f"[#D41216]{a.upper()}[/]"
            for a in "xyz"
        )
        warn = "" if self.homed == "xyz" else "   [#ff9800]position unverified[/]"
        readout.update(
            f"[{C_AXIS}]X[/] [b]{self.pos[0]:7.2f}[/b]  "
            f"[{C_AXIS}]Y[/] [b]{self.pos[1]:7.2f}[/b]  "
            f"[{C_AXIS}]Z[/] [b]{self.pos[2]:7.2f}[/b]   "
            f"[#9e9e9e]homed[/] {homed}   "
            f"[#9e9e9e]vol[/] {hi[0]:.0f}×{hi[1]:.0f}×{hi[2]:.0f}{warn}"
        )

    @staticmethod
    def _norm(value: float, lo: float, hi: float) -> float:
        if hi - lo <= 0:
            return 0.0
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))
