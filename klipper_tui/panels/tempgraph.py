"""Temperature history graph, seeded from Moonraker's temperature store."""

from __future__ import annotations

import time
from collections import deque

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from ..braille import BrailleCanvas

# Moonraker stores roughly 20 minutes at 1 Hz.
MAX_SAMPLES = 1200
RANGES = [5, 10, 20]

SERIES = [
    # key,       label,      temp colour, target colour
    ("extruder", "Hotend", "$hot", "$hot-dim"),
    ("heater_bed", "Bed", "$bed", "$bed-dim"),
]


class TempGraphPanel(Vertical):
    def __init__(self, compact: bool = False) -> None:
        # The compact variant sits on the dashboard: no controls, fixed window.
        super().__init__(
            id="tempgraph-dash" if compact else "tempgraph-panel",
            classes="panel" if compact else "",
        )
        self.compact = compact
        self.range_minutes = 10 if compact else 20
        self.show_targets = True
        self.temps: dict[str, deque[float]] = {
            k: deque(maxlen=MAX_SAMPLES) for k, _, _, _ in SERIES
        }
        self.targets: dict[str, deque[float]] = {
            k: deque(maxlen=MAX_SAMPLES) for k, _, _, _ in SERIES
        }
        self._seeded = False
        self._last_append = 0.0

    def compose(self) -> ComposeResult:
        yield Label("Temperature History", classes="panel-title")

        if not self.compact:
            with Horizontal(classes="btn-row compact-row"):
                for r in RANGES:
                    yield Button(f"{r}m", id=f"tg-range-{r}")
                yield Button("Targets", id="tg-targets")

        yield Static("", id="tg-legend")
        yield Static("", id="tg-chart", markup=True)

    def on_mount(self) -> None:
        self.set_interval(1.0, self._redraw)

    # -- data ------------------------------------------------------------------

    def seed(self, store: dict) -> None:
        """Load history from Moonraker so the chart is not empty on startup."""
        for key, *_ in SERIES:
            sensor = store.get(key) or {}
            temps = sensor.get("temperatures") or []
            targets = sensor.get("targets") or []
            if temps:
                self.temps[key].clear()
                self.temps[key].extend(temps[-MAX_SAMPLES:])
            if targets:
                self.targets[key].clear()
                self.targets[key].extend(targets[-MAX_SAMPLES:])
        self._seeded = bool(any(self.temps[k] for k, *_ in SERIES))
        self._redraw()

    def append_live(self, status: dict) -> None:
        """Append the latest reading, throttled to 1 Hz.

        Moonraker pushes status updates far faster than once a second, so
        appending every one would evict the seeded history within a couple of
        minutes and break the one-sample-per-second assumption the time window
        depends on.
        """
        # Slightly under 1s: updates arrive at ~4 Hz, so a strict 1.0 threshold
        # would only pass on the tick after, averaging 1.25s and stretching the
        # window past what the time axis claims.
        now = time.monotonic()
        if now - self._last_append < 0.95:
            return
        self._last_append = now

        for key, *_ in SERIES:
            obj = status.get(key)
            if not obj:
                continue
            temp = obj.get("temperature")
            if temp is not None:
                self.temps[key].append(float(temp))
                self.targets[key].append(float(obj.get("target") or 0.0))

    def set_range(self, minutes: int) -> None:
        self.range_minutes = minutes
        self._redraw()

    def toggle_targets(self) -> bool:
        self.show_targets = not self.show_targets
        self._redraw()
        return self.show_targets

    # -- drawing ---------------------------------------------------------------

    def _redraw(self) -> None:
        try:
            chart = self.query_one("#tg-chart", Static)
            legend = self.query_one("#tg-legend", Static)
        except Exception:
            return

        # Size from the chart widget itself, not the panel, or the axis rows
        # below the plot get clipped. The row prefix "999.9 │" is 8 columns.
        avail_w = chart.size.width or (self.size.width - 6)
        avail_h = chart.size.height or (self.size.height - 8)
        width = max(20, avail_w - 8)
        height = max(4, avail_h if self.compact else avail_h - 2)

        window = self.range_minutes * 60
        series = []
        for key, label, color, tcolor in SERIES:
            temps = list(self.temps[key])[-window:]
            targets = list(self.targets[key])[-window:]
            if temps:
                series.append((key, label, color, tcolor, temps, targets))

        if not series:
            chart.update("[$text-muted]Waiting for temperature data…[/]")
            legend.update("")
            return

        # Scale to the data, including targets when they are drawn.
        values = [v for *_, temps, _ in series for v in temps]
        if self.show_targets:
            values += [v for *_, targets in series for v in targets if v > 0]
        lo, hi = min(values), max(values)
        if hi - lo < 5:
            hi, lo = hi + 2.5, lo - 2.5
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad

        canvas = BrailleCanvas(width, height)
        for _, _, color, tcolor, temps, targets in series:
            if self.show_targets and any(t > 0 for t in targets):
                self._plot(canvas, targets, lo, hi, tcolor)
            self._plot(canvas, temps, lo, hi, color)

        rows = canvas.render()
        chart.update("\n".join(self._with_axis(rows, lo, hi, width)))

        parts = []
        for _, label, color, _, temps, targets in series:
            tgt = targets[-1] if targets else 0
            tgt_txt = f"{tgt:.0f}" if tgt else "off"
            parts.append(
                f"[{color}]██[/] {label} [b]{temps[-1]:.1f}[/b]°C "
                f"[$text-muted]/ {tgt_txt}[/]"
            )
        span = min(self.range_minutes, max(len(s[4]) for s in series) // 60 or 1)
        parts.append(f"[$text-muted]last {span}m[/]")
        legend.update("   ".join(parts))

    def _plot(self, canvas: BrailleCanvas, data: list[float],
              lo: float, hi: float, color: str) -> None:
        if len(data) < 2:
            return
        span = hi - lo or 1.0
        n = len(data)
        prev: tuple[int, int] | None = None
        for sx in range(canvas.sub_width):
            # Map each subpixel column back to a sample.
            idx = int(sx * (n - 1) / max(1, canvas.sub_width - 1))
            value = data[idx]
            sy = int((hi - value) / span * (canvas.sub_height - 1))
            sy = max(0, min(canvas.sub_height - 1, sy))
            if prev is not None:
                canvas.line(prev[0], prev[1], sx, sy, color)
            else:
                canvas.set(sx, sy, color)
            prev = (sx, sy)

    def _with_axis(self, rows: list[str], lo: float, hi: float,
                   width: int) -> list[str]:
        out = []
        n = len(rows)
        for i, row in enumerate(rows):
            value = hi - (hi - lo) * (i / max(1, n - 1))
            out.append(f"[$text-muted]{value:6.1f}[/] [$panel-lighten-2]│[/]{row}")

        if self.compact:
            # No axis furniture on the dashboard; every row goes to the plot.
            return out

        out.append(f"[$panel-lighten-2]       └{'─' * width}[/]")
        # Time runs left (oldest) to right (now).
        span = f"-{self.range_minutes}m"
        gap = max(1, width - len(span) - 3)
        out.append(f"[$text-muted]        {span}{' ' * gap}now[/]")
        return out
