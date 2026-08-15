"""Webcam panel: polls MJPEG snapshots and renders them in the terminal.

Rendering goes through textual-image, which can emit true sixel or the Kitty
graphics protocol where the terminal supports it, and falls back to unicode
half-blocks where it does not (gnome-terminal/VTE, for example, has no sixel).
"""

from __future__ import annotations

import io

import httpx
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

# Image rendering is an optional extra (it pulls in Pillow), so the rest of
# the app must work without it.
try:
    from PIL import Image as PILImage
    from textual_image.widget import (
        HalfcellImage,
        Image,
        SixelImage,
        TGPImage,
        UnicodeImage,
    )

    RENDERERS = {
        "auto": Image,
        "sixel": SixelImage,
        "tgp": TGPImage,
        "halfcell": HalfcellImage,
        "unicode": UnicodeImage,
    }
    AVAILABLE = True
except ImportError:  # pragma: no cover - depends on install extras
    PILImage = None
    RENDERERS = {}
    AVAILABLE = False

FPS_CHOICES = [1, 2, 5, 10]


class WebcamPanel(Vertical):
    def __init__(self, snapshot_url: str, renderer: str = "auto") -> None:
        super().__init__(id="webcam-panel")
        self.snapshot_url = snapshot_url
        self.renderer_name = renderer if renderer in RENDERERS else "auto"
        self.fps = 2
        self.running = True
        self._timer = None
        self._client: httpx.AsyncClient | None = None
        self._fail_count = 0
        self._aspect: float | None = None

    def compose(self) -> ComposeResult:
        yield Label("Webcam", classes="panel-title")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("Pause", id="wc-toggle", classes="-primary")
            for fps in FPS_CHOICES:
                yield Button(f"{fps} fps", id=f"wc-fps-{fps}")

        yield Static("", id="wc-info", classes="dim")
        if AVAILABLE:
            yield RENDERERS[self.renderer_name](id="wc-image")
        else:
            yield Static(
                "[$warning]Webcam support is not installed.[/]\n\n"
                "[$text-muted]Install the extra to enable it:[/]\n"
                "    pip install 'klipper-tui\\[webcam]'",
                id="wc-missing",
            )

    def on_mount(self) -> None:
        if not AVAILABLE:
            self.query_one("#wc-info", Static).update(
                "[$text-muted]image rendering unavailable[/]"
            )
            return
        self._client = httpx.AsyncClient(timeout=5.0)
        self._update_info()
        self._restart_timer()

    async def on_unmount(self) -> None:
        if self._client:
            await self._client.aclose()

    def _restart_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_interval(1 / self.fps, self._tick)

    def set_url(self, url: str) -> None:
        self.snapshot_url = url
        self._fail_count = 0
        if AVAILABLE:
            self._update_info()

    def set_fps(self, fps: int) -> None:
        self.fps = fps
        self._update_info()
        if self.running:
            self._restart_timer()

    def toggle(self) -> bool:
        self.running = not self.running
        if self.running:
            self._restart_timer()
        elif self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._update_info()
        return self.running

    def _update_info(self, extra: str = "") -> None:
        state = "[$success]live[/]" if self.running else "[$warning]paused[/]"
        self.query_one("#wc-info", Static).update(
            f"{state}   [$text-muted]{self.fps} fps[/]   "
            f"[$text-muted]renderer[/] {self.renderer_name}   "
            f"[$text-muted]{self.snapshot_url}[/]{extra}"
        )

    def _fit(self, aspect: float) -> None:  # noqa: D401
        """Size the image widget so the frame keeps its shape.

        A terminal cell is roughly twice as tall as it is wide, so the cell
        counts must be divided by that ratio to get the displayed shape.
        """
        if aspect <= 0:
            return
        image = self.query_one("#wc-image")
        avail_w = self.size.width - 4    # panel padding plus image border
        avail_h = self.size.height - 8   # title, controls, info, border
        if avail_w < 4 or avail_h < 3:
            return

        CELL = 2.0  # cell height / cell width
        if avail_w / (avail_h * CELL) > aspect:
            height = avail_h
            width = max(4, int(round(aspect * height * CELL)))
        else:
            width = avail_w
            height = max(3, int(round(width / (aspect * CELL))))

        # width/height above are the content box; the round border adds a cell
        # on each side, so grow the styled size to keep the picture's shape.
        image.styles.width = width + 2
        image.styles.height = height + 2
        self._aspect = aspect

    async def _tick(self) -> None:
        if not AVAILABLE or not self.running or self._client is None:
            return
        try:
            resp = await self._client.get(self.snapshot_url)
            resp.raise_for_status()
            frame = PILImage.open(io.BytesIO(resp.content))
            frame.load()
            if frame.height:
                self._fit(frame.width / frame.height)
            self.query_one("#wc-image").image = frame
            if self._fail_count:
                self._fail_count = 0
                self._update_info()
        except Exception as exc:
            self._fail_count += 1
            # Only surface persistent failures; a dropped frame is not news.
            if self._fail_count in (3, 30):
                self._update_info(
                    f"   [$error]{type(exc).__name__}: {exc}[/]"
                )
