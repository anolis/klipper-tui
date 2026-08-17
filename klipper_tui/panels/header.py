"""The application header: the Klipper mark, what we are talking to, the time.

Textual's own Header is one row and takes a single character for its icon,
which is not enough to draw anything recognisable. This is three rows so the
logo fits, and it earns the extra two by carrying the connection state as well
— which otherwise lives in a subtitle nobody reads.

The logo is a real image wherever the terminal can show one. Kitty and ghostty
draw it through the graphics protocol and sixel terminals through sixel, so it
is the actual artwork rather than an approximation of it; everywhere else the
same renderer falls back to half-blocks, which for a two-colour chevron is
still perfectly legible.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .. import estimate

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from ..format import duration, state_markup
from .webcam import AVAILABLE as IMAGES_AVAILABLE, RENDERERS

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "klipper-logo.png"

# The artwork is about 1.84:1, and a terminal cell is about half as wide as it
# is tall, so three rows want roughly eleven columns to keep its shape.
LOGO_ROWS = 3
LOGO_COLS = 11

# How the Klippy states read to a person.
STATE_LABELS = {
    "ready": ("ready", "$success"),
    "startup": ("starting up", "$warning"),
    "shutdown": ("shut down", "$error"),
    "error": ("error", "$error"),
    "disconnected": ("disconnected", "$error"),
}


class KlipperHeader(Horizontal):
    def __init__(self, title: str, target: str, renderer: str = "auto") -> None:
        super().__init__(id="app-header")
        self.header_title = title
        self.target = target
        # The unicode renderer is greyscale character-density, which turns a
        # two-colour logo into a grey smudge. Someone forcing it for a webcam
        # on a limited terminal still wants half-blocks here.
        if renderer == "unicode" or renderer not in RENDERERS:
            renderer = "halfcell" if renderer == "unicode" else "auto"
        self.renderer = renderer
        self._last_clock = ""
        self.job_meta: dict = {}

    def compose(self) -> ComposeResult:
        yield self._logo()
        with Vertical(id="hd-text"):
            yield Static(f"[b]{self.header_title}[/]", id="hd-title")
            yield Static(f"[$text-muted]{self.target}[/]", id="hd-target")
            yield Static("", id="hd-state")
        # The job, in the three rows the logo already costs us: what it is
        # doing, how much is left, and the two estimates side by side.
        with Vertical(id="hd-job"):
            yield Static("", id="hd-job-state")
            yield Static("", id="hd-job-slicer")
            yield Static("", id="hd-job-realtime")
        yield Static("", id="hd-clock")

    # -- the job ---------------------------------------------------------------

    def update_status(self, status: dict) -> None:
        """Show the running job, or nothing at all when there is not one."""
        stats = status.get("print_stats") or {}
        sd = status.get("virtual_sdcard") or {}
        state = (stats.get("state") or "").lower()

        if state not in ("printing", "paused"):
            self._clear_job(state)
            return

        app = self._owner()
        progress = float(sd.get("progress") or 0.0)
        elapsed = float(stats.get("print_duration") or 0.0)

        # Bytes a second, over the last few minutes. Layers were tried and
        # abandoned: a layer rate can only change when a layer does, so the
        # figure sat still for ninety seconds at a time and read as frozen.
        # File position moves with every status update, four times a second.
        estimator = getattr(app, "estimator", None)
        realtime = estimator.remaining() if estimator is not None else None
        slicer = estimate.slicer_remaining(self.job_meta, elapsed)

        self._set("hd-job-state",
                  f"{state_markup(state)} [b]{progress * 100:.1f}%[/b]"
                  f"{self._throughput(app, progress)}")
        self._set("hd-job-slicer", self._line("slicer", slicer))
        self._set("hd-job-realtime", self._line("realtime", realtime))

    @staticmethod
    def _line(label: str, remaining: float | None) -> str:
        """One estimate: how long is left, and the clock time that lands on."""
        if remaining is None:
            waiting = "still measuring…" if label == "realtime" else "—"
            return f"[$text-muted]{label:8} {waiting}[/]"
        if remaining <= 0:
            # The print has run past this estimate. Saying so beats a row of
            # dashes next to a finish time of "about now".
            return f"[$text-muted]{label:8}[/] [$warning]overrun[/]"
        done_at = datetime.now() + timedelta(seconds=remaining)
        return (f"[$text-muted]{label:8}[/] [b]{duration(remaining)}[/b]  "
                f"[$text-muted]eta {done_at.strftime('%H:%M')}[/]")

    @staticmethod
    def _throughput(app, progress: float) -> str:
        """Where in the job we are, counted in gcode commands."""
        total = getattr(app, "instruction_total", None)
        if not total:
            return ""
        # Interpolated from file position rather than counted as they run:
        # Klipper does not report a command number, and bytes read is a good
        # enough stand-in for a progress readout.
        done = int(total * progress)
        rate = ""
        estimator = getattr(app, "estimator", None)
        per_second = estimator.rate() if estimator is not None else None
        if per_second:
            rate = f" [$text-muted]· {per_second * total * 60:,.0f}/min[/]"
        return (f"  [$text-muted]instr[/] {done:,}"
                f"[$text-muted]/{total:,}[/]{rate}")

    def _owner(self):
        # self.app raises on an unmounted widget, which the tests build.
        try:
            return self.app
        except Exception:
            return None

    def set_job_metadata(self, meta: dict) -> None:
        self.job_meta = meta or {}

    def _clear_job(self, state: str) -> None:
        self._set("hd-job-state",
                  state_markup(state) if state else "")
        self._set("hd-job-slicer", "")
        self._set("hd-job-realtime", "")

    def _set(self, widget_id: str, text: str) -> None:
        try:
            self.query_one(f"#{widget_id}", Static).update(text)
        except Exception:
            pass

    def _logo(self):
        """The mark, or an empty spacer if it cannot be drawn at all."""
        if IMAGES_AVAILABLE and LOGO_PATH.exists():
            try:
                return RENDERERS[self.renderer](LOGO_PATH, id="hd-logo")
            except Exception:
                # A renderer that cannot start up costs the logo, not the app.
                pass
        return Static("", id="hd-logo")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._tick()

    def _tick(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        if now == self._last_clock:
            return
        self._last_clock = now
        try:
            self.query_one("#hd-clock", Static).update(f"[$text-muted]{now}[/]")
        except Exception:
            pass

    def set_state(self, connected: bool, klippy_state: str) -> None:
        if not connected:
            text = "[$error]no connection to Moonraker[/]"
        else:
            label, colour = STATE_LABELS.get(
                klippy_state, (klippy_state or "unknown", "$text-muted"))
            text = f"[$text-muted]klippy[/] [{colour}]{label}[/]"
        try:
            self.query_one("#hd-state", Static).update(text)
        except Exception:
            pass
