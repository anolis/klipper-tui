"""A deliberately lo-fi 3D toolhead position display, LCARS-flavoured.

The build volume is drawn as a rotating wireframe in braille cells, with the
toolhead marked and dropped to the bed so its footprint is readable.
"""

from __future__ import annotations

import json
import math

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from .. import pixelgraph
from ..braille import BrailleCanvas
from ..visibility import on_screen
from ..settings import state_path

# Domain colours resolved from the active theme; see theming.py.
C_FRAME = "$vol-frame"
C_FLOOR = "$vol-floor"
C_HEAD = "$vol-head"
C_DROP = "$vol-drop"
C_AXIS = "$accent"
C_MODEL = "$hot"

# Shades from farthest to nearest. A braille cell carries one colour, so depth
# has to be conveyed by shading rather than by any per-pixel effect.
SHADE_STEPS = 8
SHADE_MIN = 0.22      # how dark the farthest, lowest material goes
DEFAULT_MODEL_RGB = (0xd1, 0x55, 0x3d)

# Brightness mixes distance with height. There are no surface normals in a
# point cloud, so height stands in for a light above and in front: the top of
# an object catches more of it, which is what makes the form read as solid.
DEPTH_WEIGHT = 0.55
HEIGHT_WEIGHT = 0.45

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
    # Defaults at class level: the geometry tests build these with __new__,
    # and braille is the mode that needs nothing from the terminal.
    hires = False
    _image_widget = None

    def __init__(self, use_hires: bool = True,
                 renderer: str = "auto") -> None:
        super().__init__(id="position-panel")
        # The volume is nothing but diagonals and the model is a few
        # thousand shaded points, both of which braille handles badly.
        self._draw_signature: tuple | None = None
        self.hires = use_hires and pixelgraph.graphics_available(renderer)
        self._image_widget = None
        if self.hires:
            try:
                from textual_image.widget import Image as AutoImage
                self._image_widget = AutoImage(id="ps-image")
            except Exception:
                self.hires = False
        self.yaw = 0.6
        self.tilt = 0.5
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        # Off by default: rotating the model is by far the most expensive
        # thing drawn, and a still view you can turn yourself is more useful
        # than one that never stops.
        self.spinning = False
        # Deposited material, as a set of voxel keys in millimetres.
        self.model: set[tuple[int, int, int]] = set()
        self.show_model = True
        self.voxel_mm = 2.0
        self.max_voxels = 6000
        self._last_e: float | None = None
        self._job: str | None = None
        self._model_cache: list = []
        self._model_cache_key: tuple | None = None
        self._model_dirty = False
        self._visible = True
        self._view_cache_key: tuple | None = None
        self._view_cache: str = ""
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
            yield Button("Spin", id="ps-spin")

        with Horizontal(classes="btn-row compact-row"):
            yield Static("Pan", classes="row-label")
            yield Button("←", id="ps-pan-left")
            yield Button("→", id="ps-pan-right")
            yield Button("↑", id="ps-pan-up")
            yield Button("↓", id="ps-pan-down")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("+", id="ps-zoom-in")
            yield Button("−", id="ps-zoom-out")
            yield Button("Reset", id="ps-reset")
            yield Button("Model", id="ps-model", classes="-primary")
            yield Button("Clear", id="ps-model-clear", classes="-danger")

        yield Static("", id="ps-readout")
        if self.hires:
            yield self._image_widget
        else:
            yield Static("", id="ps-view", markup=True)

    def on_mount(self) -> None:
        # Redrawing a rotating model is the most expensive thing here, so it
        # only runs while the panel is actually on screen.
        self._visible = True
        self.set_interval(0.15, self._tick)
        # Persisting costs a file write, so do it on a slow timer rather than
        # on every point.
        self.set_interval(15.0, self._persist_model)

    def on_unmount(self) -> None:
        self._persist_model()

    def _tick(self) -> None:
        if not on_screen(self):
            return
        if self.spinning:
            self.yaw = (self.yaw + 0.03) % (2 * math.pi)
        self._redraw()

    # -- data ------------------------------------------------------------------

    def record_motion(self, status: dict) -> None:
        """Accumulate material. Called on every update, unlike the redraw."""
        self._record_motion(status)

    def update_status(self, status: dict) -> None:
        if not on_screen(self):
            return
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

    def _model_shades(self) -> list[str]:
        """A far-to-near ramp derived from the theme's material colour."""
        base = DEFAULT_MODEL_RGB
        try:
            raw = (self.app.current_theme.variables or {}).get("hot")
            if isinstance(raw, str) and raw.startswith("#") and len(raw) == 7:
                base = tuple(int(raw[i:i + 2], 16) for i in (1, 3, 5))
        except Exception:
            pass

        shades = []
        for step in range(SHADE_STEPS):
            factor = SHADE_MIN + (1.0 - SHADE_MIN) * step / (SHADE_STEPS - 1)
            shades.append("#%02x%02x%02x" % tuple(
                max(0, min(255, int(channel * factor))) for channel in base
            ))
        return shades

    def _draw_model(self, canvas: BrailleCanvas,
                    fit: tuple[float, float, float]) -> None:
        """Draw deposited material, shaded so the shape reads as solid.

        Only the nearest point per pixel is kept, which gives occlusion without
        sorting, and brightness combines distance with height so the form has
        depth instead of being a flat mass of one colour. The result is cached
        against the view, so a still model costs nothing to redraw.
        """
        # Keyed on the drawing units, not the cell count: dropping to a
        # quarter of the pixels while spinning leaves the cell count alone but
        # changes every projected coordinate, and a cell-count key would serve
        # the previous resolution's points at the new scale.
        key = (self.yaw, self.tilt, self.zoom, self.pan[0], self.pan[1],
               len(self.model), canvas.sub_width, canvas.sub_height)
        if key != self._model_cache_key:
            self._model_cache_key = key
            self._model_cache = self._build_model_pixels(fit)
        for (sx, sy), shade in self._model_cache:
            canvas.set(sx, sy, shade)

    def _build_model_pixels(self, fit: tuple[float, float, float]) -> list:
        lo, hi = self.limits
        step = self.voxel_mm
        ax, ay, az = self._aspect()
        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        cos_t, sin_t = math.cos(self.tilt), math.sin(self.tilt)
        scale, off_x, off_y = fit
        sx_lo, sy_lo = lo[0], lo[1]
        span_x = max(1e-6, hi[0] - lo[0])
        span_y = max(1e-6, hi[1] - lo[1])
        span_z = max(1e-6, hi[2] - lo[2])

        # One pass: for each pixel remember only the nearest point, along with
        # the values needed to shade it.
        nearest: dict[tuple[int, int], tuple[float, float]] = {}
        for vx, vy, vz in self.model:
            x = ((vx * step - sx_lo) / span_x - 0.5) * ax
            y = ((vy * step - sy_lo) / span_y - 0.5) * ay
            z = ((vz * step - lo[2]) / span_z - 0.5) * az
            rx = x * cos_y - y * sin_y
            ry = x * sin_y + y * cos_y
            depth = ry * cos_t - z * sin_t
            pixel = (int(off_x + rx * scale),
                     int(off_y + (-ry * sin_t - z * cos_t) * scale))
            previous = nearest.get(pixel)
            if previous is None or depth < previous[0]:
                nearest[pixel] = (depth, z)

        if not nearest:
            return []

        depths = [v[0] for v in nearest.values()]
        heights = [v[1] for v in nearest.values()]
        near, far = min(depths), max(depths)
        low, high = min(heights), max(heights)
        depth_spread = (far - near) or 1.0
        height_spread = (high - low) or 1.0
        shades = self._model_shades()
        top = SHADE_STEPS - 1

        pixels = []
        for pixel, (depth, height) in nearest.items():
            level = (DEPTH_WEIGHT * ((far - depth) / depth_spread)
                     + HEIGHT_WEIGHT * ((height - low) / height_spread))
            pixels.append((pixel, shades[max(0, min(top, int(level * top)))]))
        return pixels

    def _record_motion(self, status: dict) -> None:
        """Accumulate deposited material from the live motion report.

        The extruder axis only advances while material is being laid down, so
        a position sampled with a rising E is a point on the printed object.
        """
        stats = status.get("print_stats") or {}
        job = stats.get("filename") or None
        if job != self._job:
            # A different job starts a fresh model, but the same job picked up
            # again — after restarting this app mid-print — restores what was
            # already drawn.
            self._persist_model()
            self._job = job
            self._last_e = None
            self.model = self._load_model(job) if job else set()
            self._model_cache_key = None

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
            self._model_dirty = True

    # -- persistence -----------------------------------------------------------

    @staticmethod
    def _model_file():
        return state_path("model.json")

    def _load_model(self, job: str) -> set:
        """Restore the model for this job, if the saved one belongs to it."""
        path = self._model_file()
        if not path.is_file():
            return set()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return set()
        if data.get("job") != job:
            return set()
        try:
            voxels = {tuple(int(v) for v in point)
                      for point in data.get("voxels", [])}
        except (TypeError, ValueError):
            return set()
        # A saved model from a different grid size would be misplaced.
        if data.get("voxel_mm") != self.voxel_mm:
            return set()
        return {v for v in voxels if len(v) == 3}

    def _persist_model(self) -> None:
        if not self._model_dirty:
            return
        self._model_dirty = False
        self._visible = True
        self._view_cache_key: tuple | None = None
        self._view_cache: str = ""
        path = self._model_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "job": self._job,
                "voxel_mm": self.voxel_mm,
                "voxels": [list(v) for v in self.model],
            }
            # Write beside the target then move, so an interrupted write
            # cannot leave a truncated file behind.
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload))
            temporary.replace(path)
        except OSError:
            pass

    def toggle_model(self) -> bool:
        self.show_model = not self.show_model
        self._redraw()
        return self.show_model

    def clear_model(self) -> None:
        self.model.clear()
        self._model_cache_key = None
        self._model_dirty = True
        self._persist_model()
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
        """Shift the view. Positive dy moves it up."""
        # Pan in units of the fitted view, so it feels the same at any zoom.
        self.pan[0] += dx / self.zoom
        self.pan[1] += dy / self.zoom
        self._redraw()


    def centre_on(self, fx: float, fy: float) -> None:
        """Bring the point at these view fractions to the middle.

        Both offsets are applied as a fraction of the canvas, so the shift
        needed is simply how far the point is from the centre — no zoom term,
        unlike a nudge.
        """
        self.pan[0] += 0.5 - fx
        self.pan[1] += fy - 0.5
        self._model_cache_key = None
        self._redraw()

    def _click_fractions(self, event, view_id: str):
        """Where a click landed inside the drawing, as fractions of it."""
        try:
            view = self.query_one(view_id)
        except Exception:
            return None
        region = view.region
        if not region.width or not region.height:
            return None
        fx = (event.screen_x - region.x) / region.width
        fy = (event.screen_y - region.y) / region.height
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            return None      # a click on the buttons, not the picture
        return fx, fy

    def on_click(self, event) -> None:
        where = self._click_fractions(event, "#ps-view")
        if where is not None:
            self.centre_on(*where)

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
        off_y = ch / 2 - (max(ys) + min(ys)) / 2 * scale - self.pan[1] * ch
        return scale, off_x, off_y

    def _project(self, u: float, v: float, w: float,
                 fit: tuple[float, float, float]) -> tuple[int, int]:
        scale, off_x, off_y = fit
        rx, ry = self._raw(u, v, w)
        return (int(off_x + rx * scale), int(off_y + ry * scale))

    # -- drawing ---------------------------------------------------------------

    def _make_canvas(self, width: int, height: int):
        """Full pixels when still, a quarter of them while spinning.

        A static view is redrawn only when the toolhead moves, so it can
        afford every pixel the terminal has. Spinning redraws six times a
        second, and at full size that is a quarter of a core and several
        megabytes a second down the pipe. Halving each axis is a quarter of
        the pixels, and a frame that is on screen for 150ms does not need
        them.
        """
        if not self.hires:
            return BrailleCanvas(width, height)
        # Budgeted rather than full size: the volume redraws as the toolhead moves.
        pixels_w, pixels_h = pixelgraph.plot_size(
            width, height, pixelgraph.LIVE_PIXELS)
        if self.spinning:
            pixels_w, pixels_h = max(16, pixels_w // 2), max(16, pixels_h // 2)
        return pixelgraph.PixelCanvas(
            pixels_w, pixels_h,
            background=pixelgraph.resolve(self.app, "$surface"),
            resolve=lambda token: pixelgraph.resolve(self.app, token),
            stroke=1 if self.spinning else 2,
            cells=(width, height))

    def _redraw(self) -> None:
        try:
            readout = self.query_one("#ps-readout", Static)
            view = self._image_widget if self.hires \
                else self.query_one("#ps-view", Static)
        except Exception:
            return

        width = max(20, (view.size.width or self.size.width) - 2)
        height = max(8, (view.size.height or 16) - 1)

        # Redraw only when the picture would differ. The panel ticks about
        # seven times a second so that spinning is smooth, but a still view of
        # a stationary toolhead is the same picture every time — and in image
        # mode each redraw hands the terminal a fresh megabyte to transmit,
        # which starved the toolpath sharing the tab.
        signature = (round(self.yaw, 4), round(self.tilt, 4), self.zoom,
                     round(self.pan[0], 4), round(self.pan[1], 4),
                     tuple(round(v, 2) for v in self.pos), width, height,
                     self.spinning, self.show_model, len(self.model),
                     tuple(self.limits[1]))
        if signature == self._draw_signature:
            return
        self._draw_signature = signature

        canvas = self._make_canvas(width, height)
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
            self._draw_model(canvas, fit)

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
        arm = pixelgraph.marker_arm(canvas)
        for dx in range(-arm, arm + 1):
            canvas.set(head[0] + dx, head[1], C_HEAD)
        for dy in range(-arm, arm + 1):
            canvas.set(head[0], head[1] + dy, C_HEAD)

        if self.hires:
            pixelgraph.show(view, canvas.image)
        else:
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
