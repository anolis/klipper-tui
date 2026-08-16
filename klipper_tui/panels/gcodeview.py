"""Toolpath view: the current layer, drawn as the printer works through it."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from ..braille import BrailleCanvas
from ..gcode import Layer, Toolpath, layer_for_position

C_DONE = "$hot"        # already laid down
C_TODO = "$vol-floor"  # still to come on this layer
C_HEAD = "$vol-head"   # where the nozzle is


class GcodeViewPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="gcodeview-panel", classes="panel")
        self.gcode_layers: list[Layer] = []
        self.toolpath: Toolpath | None = None
        self.layer_index: int | None = None
        self.follow = True
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.file_position = 0
        self.head: tuple[float, float] | None = None
        self.status_text = "No job loaded."
        # Framing is accumulated across layers so the view does not jump as
        # the object changes shape.
        self.frame: tuple[float, float, float, float] | None = None
        self._cache_key: tuple | None = None
        self._cache: list = []

    def compose(self) -> ComposeResult:
        yield Label("Toolpath", classes="panel-title")
        with Horizontal(classes="btn-row compact-row"):
            yield Button("Follow", id="gv-follow", classes="-primary")
            yield Button("−1", id="gv-prev")
            yield Button("+1", id="gv-next")
            yield Button("+", id="gv-zoom-in")
            yield Button("−", id="gv-zoom-out")
            yield Button("Fit", id="gv-fit")

        with Horizontal(classes="btn-row compact-row"):
            yield Static("Pan", classes="row-label")
            yield Button("←", id="gv-pan-left")
            yield Button("→", id="gv-pan-right")
            yield Button("↑", id="gv-pan-up")
            yield Button("↓", id="gv-pan-down")
        yield Static("", id="gv-info", classes="dim")
        yield Static("", id="gv-view", markup=True)

    def on_mount(self) -> None:
        self.set_interval(0.5, self._redraw)
        self._redraw()

    # -- state -----------------------------------------------------------------

    def set_layers(self, layers: list[Layer]) -> None:
        self.gcode_layers = layers
        self.layer_index = None
        self.toolpath = None
        self.frame = None
        self._cache_key = None
        self.status_text = ("No layers found in this file."
                            if not layers else "")

    def set_toolpath(self, index: int, toolpath: Toolpath) -> None:
        self.layer_index = index
        self.toolpath = toolpath
        bounds = toolpath.bounds()
        if bounds:
            if self.frame is None:
                self.frame = bounds
            else:
                self.frame = (
                    min(self.frame[0], bounds[0]), min(self.frame[1], bounds[1]),
                    max(self.frame[2], bounds[2]), max(self.frame[3], bounds[3]),
                )
        self._cache_key = None

    def update_status(self, status: dict) -> None:
        sd = status.get("virtual_sdcard") or {}
        self.file_position = int(sd.get("file_position") or 0)
        move = status.get("gcode_move") or {}
        position = move.get("gcode_position")
        if position and len(position) >= 2:
            self.head = (float(position[0]), float(position[1]))

    def wanted_layer(self) -> int | None:
        """The layer that should be on screen."""
        if not self.gcode_layers:
            return None
        if self.follow:
            return layer_for_position(self.gcode_layers, self.file_position)
        return self.layer_index

    def step(self, delta: int) -> None:
        if not self.gcode_layers:
            return
        self.follow = False
        current = self.layer_index if self.layer_index is not None else 0
        self.layer_index = max(0, min(len(self.gcode_layers) - 1, current + delta))
        self.toolpath = None      # the app parses the new layer
        self._cache_key = None

    def toggle_follow(self) -> bool:
        self.follow = not self.follow
        self._cache_key = None
        return self.follow

    def zoom_by(self, factor: float) -> None:
        self.zoom = max(0.5, min(20.0, self.zoom * factor))
        self._cache_key = None
        self._redraw()

    def pan_by(self, dx: float, dy: float) -> None:
        # Pan in fractions of the view, so it feels the same at any zoom.
        self.pan[0] += dx / self.zoom
        self.pan[1] += dy / self.zoom
        self._cache_key = None
        self._redraw()

    def refit(self) -> None:
        """Reframe on the layer in view and undo any zoom or pan."""
        self.frame = self.toolpath.bounds() if self.toolpath else None
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self._cache_key = None
        self._redraw()

    # -- drawing ---------------------------------------------------------------

    def _redraw(self) -> None:
        try:
            info = self.query_one("#gv-info", Static)
            view = self.query_one("#gv-view", Static)
        except Exception:
            return

        if not self.toolpath or not self.frame:
            info.update(f"[$text-muted]{self.status_text or 'Loading…'}[/]")
            view.update("")
            return

        width = max(20, (view.size.width or self.size.width) - 2)
        height = max(8, (view.size.height or 18) - 1)

        # Only the printed fraction changes moment to moment; redraw when it
        # advances enough to matter, not on every tick.
        key = (self.layer_index, width, height, self.file_position // 4096,
               self.frame, self.zoom, self.pan[0], self.pan[1])
        if key != self._cache_key:
            self._cache_key = key
            self._cache = self._render_toolpath(width, height)
        view.update("\n".join(self._cache))

        layer = self.gcode_layers[self.layer_index] if self.layer_index is not None \
            else None
        done = sum(1 for s in self.toolpath.segments
                   if s.extruding and s.offset <= self.file_position)
        total = sum(1 for s in self.toolpath.segments if s.extruding)
        info.update(
            f"[$text-muted]Layer[/] [b]{(self.layer_index or 0) + 1}"
            f"[/b][$text-muted]/{len(self.gcode_layers)}[/]   "
            f"[$text-muted]z[/] [b]{layer.z if layer else 0:.2f}[/b]   "
            f"[$text-muted]moves[/] [b]{done}[/b][$text-muted]/{total}[/]   "
            f"{'[$success]following[/]' if self.follow else '[$warning]held[/]'}"
            f"   [$text-muted]zoom[/] {self.zoom:.1f}×"
        )

    def _render_toolpath(self, width: int, height: int) -> list[str]:
        canvas = BrailleCanvas(width, height)
        min_x, min_y, max_x, max_y = self.frame
        span_x = max(1e-6, max_x - min_x)
        span_y = max(1e-6, max_y - min_y)
        # Braille subpixels are square, so keep one scale for both axes and
        # centre what is left over.
        scale = (min(canvas.sub_width / span_x, canvas.sub_height / span_y)
                 * 0.96 * self.zoom)
        off_x = ((canvas.sub_width - span_x * scale) / 2
                 + self.pan[0] * canvas.sub_width)
        off_y = ((canvas.sub_height - span_y * scale) / 2
                 - self.pan[1] * canvas.sub_height)

        def place(x: float, y: float) -> tuple[int, int]:
            # Bed Y grows away from the viewer; screen Y grows downward.
            return (int(off_x + (x - min_x) * scale),
                    int(canvas.sub_height - off_y - (y - min_y) * scale))

        for segment in self.toolpath.segments:
            if not segment.extruding:
                continue  # travel moves would bury the shape in straight lines
            colour = C_DONE if segment.offset <= self.file_position else C_TODO
            canvas.line(*place(segment.x0, segment.y0),
                        *place(segment.x1, segment.y1), colour)

        if self.head:
            hx, hy = place(*self.head)
            for dx in range(-2, 3):
                canvas.set(hx + dx, hy, C_HEAD)
            for dy in range(-2, 3):
                canvas.set(hx, hy + dy, C_HEAD)

        return canvas.render()
