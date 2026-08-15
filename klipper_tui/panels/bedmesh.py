"""Bed mesh panel: run calibration and render the mesh as a colour heightmap."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

# Blue (low) -> green (nominal) -> red (high), matching Mainsail's heightmap.
GRADIENT = [
    "$accent", "#03a9f4", "#00bcd4", "#009688",
    "$success", "#8bc34a", "#cddc39", "#ffeb3b",
    "#ffc107", "$warning", "#ff5722", "$error",
]


class BedMeshPanel(Vertical):
    # Rough wall-clock cost of one probe point, including travel. Only used
    # for the estimate shown next to the probe count.
    SECONDS_PER_POINT = 2.0

    def __init__(self) -> None:
        super().__init__(id="bedmesh-panel")
        self.algorithm = "lagrange"
        self._count_seeded = False

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
