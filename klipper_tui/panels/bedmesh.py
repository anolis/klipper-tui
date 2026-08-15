"""Bed mesh panel: run calibration and render the mesh as a colour heightmap."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

# Blue (low) -> green (nominal) -> red (high), matching Mainsail's heightmap.
GRADIENT = [
    "$accent", "#03a9f4", "#00bcd4", "#009688",
    "$success", "#8bc34a", "#cddc39", "#ffeb3b",
    "#ffc107", "$warning", "#ff5722", "$error",
]


class BedMeshPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="bedmesh-panel")

    def compose(self) -> ComposeResult:
        yield Label("Bed Mesh", classes="panel-title")

        with Horizontal(classes="btn-row"):
            yield Button("Calibrate", id="bm-calibrate", classes="-primary")
            yield Button("Load Profile", id="bm-load")
            yield Button("Save Config", id="bm-save", classes="-success")
            yield Button("Clear", id="bm-clear", classes="-danger")

        yield Static("", id="bm-info", classes="dim")
        yield Static("", id="heightmap")

    def update_status(self, status: dict) -> None:
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
