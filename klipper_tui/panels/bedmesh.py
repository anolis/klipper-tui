"""Bed mesh panel: run calibration and render the mesh as a colour heightmap."""

from __future__ import annotations

import re
import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# Blue (low) -> green (nominal) -> red (high), matching Mainsail's heightmap.
# Deliberately literal, not theme tokens: the heightmap encodes measured
# deviation, so the scale must mean the same thing under every theme.
GRADIENT = [
    "#2196f3", "#03a9f4", "#00bcd4", "#009688",
    "#4caf50", "#8bc34a", "#cddc39", "#ffeb3b",
    "#ffc107", "#ff9800", "#ff5722", "#d41216",
]


# Give up on the live view if probing goes quiet without producing a mesh.
PROBE_IDLE_TIMEOUT = 120.0

# Klipper reports each probe result on the console. The wording changed
# between releases, so both forms are accepted.
PROBE_LINE = re.compile(
    r"probe:?\s+at\s+(-?[\d.]+),\s*(-?[\d.]+)\s+"
    r"(?:is|bed will contact at)\s+z\s*=\s*(-?[\d.]+)",
    re.IGNORECASE,
)


class BedMeshPanel(Vertical):
    # Rough wall-clock cost of one probe point, including travel. Only used
    # for the estimate shown next to the probe count.
    SECONDS_PER_POINT = 2.0

    def __init__(self) -> None:
        super().__init__(id="bedmesh-panel")
        self.algorithm = "lagrange"
        self._count_seeded = False
        # Live probing state, populated from console output while a mesh runs.
        self.live: dict[tuple[int, int], float] = {}
        self.live_expected: tuple[int, int] | None = None
        self.live_joined = False          # joined a run already in progress
        self._last_probe_at = 0.0
        self.bounds: tuple[float, float, float, float] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Bed Mesh", classes="panel-title")

        with Horizontal(classes="btn-row"):
            yield Button("Calibrate", id="bm-calibrate", classes="-primary")
            yield Button("Load Profile", id="bm-load")
            yield Button("Save Config", id="bm-save", classes="-success")
            yield Button("Clear", id="bm-clear", classes="-danger")

        with Horizontal(classes="btn-row"):
            yield Input(placeholder="probe count, e.g. 10 or 10,15",
                        id="bm-count")
            yield Static("", id="bm-estimate", classes="setting-label")

        yield Static("", id="bm-info", classes="dim")
        yield Static("", id="heightmap")

    def update_status(self, status: dict) -> None:
        cfg = (status.get("configfile") or {}).get("config") or {}
        bm_cfg = cfg.get("bed_mesh") or {}
        self.algorithm = str(bm_cfg.get("algorithm", "lagrange")).lower()
        self.bounds = self._parse_bounds(bm_cfg)
        if not self._count_seeded:
            configured = str(bm_cfg.get("probe_count", "")).replace(" ", "")
            if configured:
                try:
                    self.query_one("#bm-count", Input).value = configured
                    self._count_seeded = True
                    self.refresh_estimate()
                except Exception:
                    pass

        mesh = status.get("bed_mesh", {})
        matrix = mesh.get("probed_matrix") or []

        if self.live_expected is not None:
            if matrix and any(matrix):
                # Klipper clears the mesh while probing and sets it when done,
                # so a populated matrix means the run finished.
                self.stop_live()
            elif time.monotonic() - self._last_probe_at > PROBE_IDLE_TIMEOUT:
                # Probing stopped without producing a mesh: cancelled or failed.
                self.stop_live()
            else:
                return  # still probing; the live grid owns the display
        profile = mesh.get("profile_name") or ""
        note = ""

        # An empty probed_matrix means no mesh is active. Fall back to a saved
        # profile so the heightmap is still viewable, and flag that it is not
        # actually applied to the current print.
        if not matrix or not any(matrix):
            saved = mesh.get("profiles") or {}
            if saved:
                name = "default" if "default" in saved else next(iter(saved))
                matrix = saved[name].get("points") or []
                profile = f"{name} (saved)"
                note = "   [$warning]not loaded — mesh is NOT active[/]"

        if not matrix or not any(matrix):
            self.query_one("#bm-info", Static).update(
                "[$text-muted]No mesh loaded. Run Calibrate to probe the bed.[/]"
            )
            self.query_one("#heightmap", Static).update("")
            return

        flat = [z for row in matrix for z in row]
        lo, hi = min(flat), max(flat)
        rng = hi - lo

        self.query_one("#bm-info", Static).update(
            f"[$text-muted]Profile[/] [b]{profile}[/b]   "
            f"[$text-muted]min[/] [b]{lo:+.3f}[/b]   "
            f"[$text-muted]max[/] [b]{hi:+.3f}[/b]   "
            f"[$text-muted]range[/] [b]{rng:.3f}mm[/b]   "
            f"[$text-muted]{len(matrix[0])}x{len(matrix)} points[/]{note}"
        )
        self.query_one("#heightmap", Static).update(
            self._render_heightmap(matrix, lo, hi)
        )

    # -- live probing ----------------------------------------------------------

    @staticmethod
    def _parse_bounds(bm_cfg: dict) -> tuple[float, float, float, float] | None:
        def pair(value) -> tuple[float, float] | None:
            try:
                a, b = str(value).split(",")
                return float(a), float(b)
            except (ValueError, AttributeError):
                return None

        low = pair(bm_cfg.get("mesh_min"))
        high = pair(bm_cfg.get("mesh_max"))
        if low and high:
            return low[0], low[1], high[0], high[1]
        return None

    def start_live(self, count: tuple[int, int], joined: bool = False) -> None:
        self.live.clear()
        self.live_expected = count
        self.live_joined = joined
        self._last_probe_at = time.monotonic()
        self._redraw_live()

    def stop_live(self) -> None:
        self.live.clear()
        self.live_expected = None
        self.live_joined = False

    def add_probe(self, x: float, y: float, z: float) -> bool:
        """Place one probed point on the grid. False if it cannot be mapped."""
        if self.live_expected is None or self.bounds is None:
            return False
        x_cnt, y_cnt = self.live_expected
        min_x, min_y, max_x, max_y = self.bounds
        span_x = max_x - min_x
        span_y = max_y - min_y
        if span_x <= 0 or span_y <= 0:
            return False
        # Klipper probes in a serpentine order, so index by position rather
        # than by arrival order.
        col = round((x - min_x) / span_x * (x_cnt - 1)) if x_cnt > 1 else 0
        row = round((y - min_y) / span_y * (y_cnt - 1)) if y_cnt > 1 else 0
        col = max(0, min(x_cnt - 1, col))
        row = max(0, min(y_cnt - 1, row))
        self.live[(row, col)] = z
        self._last_probe_at = time.monotonic()
        self._redraw_live()
        return True

    def _redraw_live(self) -> None:
        if self.live_expected is None:
            return
        try:
            info = self.query_one("#bm-info", Static)
            heightmap = self.query_one("#heightmap", Static)
        except Exception:
            return

        x_cnt, y_cnt = self.live_expected
        total = x_cnt * y_cnt
        done = len(self.live)
        values = list(self.live.values())
        lo = min(values) if values else 0.0
        hi = max(values) if values else 0.0

        note = ("   [$text-muted]joined in progress; earlier points are "
                "not shown[/]" if self.live_joined else "")
        info.update(
            f"[$accent]probing[/]   [$text-muted]point[/] [b]{done}[/b]"
            f"[$text-muted]/{total}[/]   "
            f"[$text-muted]min[/] [b]{lo:+.3f}[/b]   "
            f"[$text-muted]max[/] [b]{hi:+.3f}[/b]   "
            f"[$text-muted]range[/] [b]{hi - lo:.3f}mm[/]{note}"
        )

        rng = (hi - lo) or 1.0
        lines = []
        for row in reversed(range(y_cnt)):
            cells = []
            for col in range(x_cnt):
                z = self.live.get((row, col))
                if z is None:
                    cells.append("[$panel-lighten-1]··[/]")
                else:
                    idx = int((z - lo) / rng * (len(GRADIENT) - 1))
                    idx = max(0, min(len(GRADIENT) - 1, idx))
                    cells.append(f"[{GRADIENT[idx]}]██[/]")
            lines.append("".join(cells))
        heightmap.update("\n".join(lines))

    def parse_count(self) -> tuple[int, int] | None:
        """Read the probe count field as an (x, y) pair."""
        raw = self.query_one("#bm-count", Input).value.strip()
        if not raw:
            return None
        parts = [p.strip() for p in raw.replace("x", ",").split(",") if p.strip()]
        try:
            values = [int(p) for p in parts]
        except ValueError:
            return None
        if len(values) == 1:
            return values[0], values[0]
        if len(values) == 2:
            return values[0], values[1]
        return None

    def validate_count(self, count: tuple[int, int]) -> str | None:
        """Klipper's own constraints, checked before we send anything."""
        x, y = count
        if x < 3 or y < 3:
            return "Probe count must be at least 3 per axis."
        if self.algorithm == "lagrange" and max(x, y) > 6:
            return ("Lagrange interpolation cannot exceed 6 per axis. "
                    "Set algorithm: bicubic in printer.cfg for larger grids.")
        if self.algorithm == "bicubic" and min(x, y) < 4 and max(x, y) > 6:
            return ("Bicubic cannot combine 3 points on one axis with more "
                    "than 6 on the other.")
        return None

    def refresh_estimate(self) -> None:
        try:
            widget = self.query_one("#bm-estimate", Static)
        except Exception:
            return
        count = self.parse_count()
        if count is None:
            widget.update("[$text-muted]blank uses the configured count[/]")
            return
        problem = self.validate_count(count)
        if problem:
            widget.update(f"[$error]{problem}[/]")
            return
        points = count[0] * count[1]
        seconds = points * self.SECONDS_PER_POINT
        widget.update(
            f"[$text-muted]{count[0]}×{count[1]} = [/]{points} points"
            f"[$text-muted], roughly {self._duration(seconds)}[/]"
        )

    @staticmethod
    def _duration(seconds: float) -> str:
        if seconds < 90:
            return f"{seconds:.0f}s"
        if seconds < 5400:
            return f"{seconds / 60:.0f} min"
        return f"{seconds / 3600:.1f} hours"

    def calibrate_gcode(self) -> str:
        count = self.parse_count()
        if count is None:
            return "BED_MESH_CALIBRATE"
        return f"BED_MESH_CALIBRATE PROBE_COUNT={count[0]},{count[1]}"

    def _render_heightmap(self, matrix: list[list[float]], lo: float, hi: float) -> str:
        rng = hi - lo or 1.0
        lines = []

        # Front of the bed is row 0 in Klipper's matrix; print it last so the
        # display matches the physical bed orientation seen from the front.
        for row in reversed(matrix):
            cells = []
            for z in row:
                idx = int((z - lo) / rng * (len(GRADIENT) - 1))
                idx = max(0, min(len(GRADIENT) - 1, idx))
                cells.append(f"[{GRADIENT[idx]}]██[/]")
            cells.append(f" [$text-muted]{max(row):+.3f}[/]")
            lines.append("".join(cells))

        legend = "".join(f"[{c}]█[/]" for c in GRADIENT)
        lines.append("")
        lines.append(f"[$text-muted]{lo:+.3f}[/] {legend} [$text-muted]{hi:+.3f}[/]")
        return "\n".join(lines)
