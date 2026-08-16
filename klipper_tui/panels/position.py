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

# Domain colours resolved from the active theme; see theming.py.
C_FRAME = "$vol-frame"
C_FLOOR = "$vol-floor"
C_HEAD = "$vol-head"
C_DROP = "$vol-drop"
C_AXIS = "$accent"
C_MODEL = "$hot"

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
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.spinning = True
        # Deposited material, as a set of voxel keys in millimetres.
        self.model: set[tuple[int, int, int]] = set()
        self.show_model = True
        self.voxel_mm = 2.0
        self.max_voxels = 6000
        self._last_e: float | None = None
        self._job: str | None = None
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
            yield Button("+", id="ps-zoom-in")
            yield Button("−", id="ps-zoom-out")
            yield Button("Reset", id="ps-reset")

        with Horizontal(classes="btn-row compact-row"):
            yield Static("Pan", classes="row-label")
            yield Button("←", id="ps-pan-left")
            yield Button("→", id="ps-pan-right")
            yield Button("↑", id="ps-pan-up")
            yield Button("↓", id="ps-pan-down")
            yield Button("Model", id="ps-model", classes="-primary")
            yield Button("Clear", id="ps-model-clear", classes="-danger")

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
        self._record_motion(status)
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

    def _record_motion(self, status: dict) -> None:
        """Accumulate deposited material from the live motion report.

        The extruder axis only advances while material is being laid down, so
        a position sampled with a rising E is a point on the printed object.
        """
        stats = status.get("print_stats") or {}
        job = stats.get("filename") or None
        if job != self._job:
            # A different job (or none) starts a fresh model.
            self._job = job
            self.model.clear()
            self._last_e = None

        report = status.get("motion_report") or {}
        live = report.get("live_position")
        if not live or len(live) < 4:
            return
        x, y, z, e = (float(v) for v in live[:4])

        previous, self._last_e = self._last_e, e
        if previous is None or e <= previous:
            return  # travel move or retraction, nothing deposited
        if stats.get("state") not in ("printing", "paused"):
            return

        if len(self.model) < self.max_voxels:
            step = self.voxel_mm
            self.model.add((
                int(x / step), int(y / step), int(z / step),
            ))

    def toggle_model(self) -> bool:
        self.show_model = not self.show_model
        self._redraw()
        return self.show_model

    def clear_model(self) -> None:
        self.model.clear()
        self._redraw()

    def rotate(self, dyaw: float = 0.0, dtilt: float = 0.0) -> None:
        self.yaw = (self.yaw + dyaw) % (2 * math.pi)
        self.tilt = max(-1.4, min(1.4, self.tilt + dtilt))
        self._redraw()

    def toggle_spin(self) -> bool:
        self.spinning = not self.spinning
        return self.spinning

    def zoom_by(self, factor: float) -> None:
        self.zoom = max(0.4, min(6.0, self.zoom * factor))
        self._redraw()

    def pan_by(self, dx: float, dy: float) -> None:
        # Pan in units of the fitted view, so it feels the same at any zoom.
        self.pan[0] += dx / self.zoom
        self.pan[1] += dy / self.zoom
        self._redraw()

    def reset_view(self) -> None:
        self.yaw, self.tilt = 0.6, 0.5
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self._redraw()

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
        # Screen y grows downward, so both terms are negated: the back of the
        # bed has to sit higher up the screen than the front, and greater Z
        # higher still. Without the sign on the depth term the projection is
        # left-handed and the volume renders mirrored.
        return (rx, -ry * sin_t - z * cos_t)

    def _fit(self, cw: int, ch: int) -> tuple[float, float, float]:
        """Scale and offsets that fit the whole volume at this rotation."""
        pts = [self._raw(*c) for c in CORNERS]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_x = max(xs) - min(xs) or 1.0
        span_y = max(ys) - min(ys) or 1.0
        scale = min(cw / span_x, ch / span_y) * 0.88 * self.zoom
        off_x = cw / 2 - (max(xs) + min(xs)) / 2 * scale + self.pan[0] * cw
        off_y = ch / 2 - (max(ys) + min(ys)) / 2 * scale + self.pan[1] * ch
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

        # Deposited material, drawn under the toolhead so the marker stays on
        # top. Height shades the points so layers read apart.
        if self.show_model and self.model:
            step = self.voxel_mm
            for vx, vy, vz in self.model:
                mu = self._norm(vx * step, lo[0], hi[0])
                mv = self._norm(vy * step, lo[1], hi[1])
                mw = self._norm(vz * step, lo[2], hi[2])
                canvas.set(*self._project(mu, mv, mw, fit), C_MODEL)

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
            f"[$success]{a.upper()}[/]" if a in self.homed
            else f"[$error]{a.upper()}[/]"
            for a in "xyz"
        )
        warn = "" if self.homed == "xyz" else "   [$warning]position unverified[/]"
        readout.update(
            f"[{C_AXIS}]X[/] [b]{self.pos[0]:7.2f}[/b]  "
            f"[{C_AXIS}]Y[/] [b]{self.pos[1]:7.2f}[/b]  "
            f"[{C_AXIS}]Z[/] [b]{self.pos[2]:7.2f}[/b]   "
            f"[$text-muted]homed[/] {homed}   "
            f"[$text-muted]vol[/] {hi[0]:.0f}×{hi[1]:.0f}×{hi[2]:.0f}   "
            f"[$text-muted]zoom[/] {self.zoom:.1f}×   "
            f"[$text-muted]model[/] "
            f"{len(self.model) if self.show_model else 'off'}{warn}"
        )

    @staticmethod
    def _norm(value: float, lo: float, hi: float) -> float:
        if hi - lo <= 0:
            return 0.0
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))
