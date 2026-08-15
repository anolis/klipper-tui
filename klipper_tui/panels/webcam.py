"""Webcam panel: polls MJPEG snapshots and renders them in the terminal.

Rendering goes through textual-image, which can emit true sixel or the Kitty
graphics protocol where the terminal supports it, and falls back to unicode
half-blocks where it does not (gnome-terminal/VTE, for example, has no sixel).
"""

from __future__ import annotations

import io

import httpx
from PIL import Image as PILImage
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static
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

    def compose(self) -> ComposeResult:
        yield Label("Webcam", classes="panel-title")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("Pause", id="wc-toggle", classes="-primary")
            for fps in FPS_CHOICES:
                yield Button(f"{fps} fps", id=f"wc-fps-{fps}")

        yield Static("", id="wc-info", classes="dim")
        image_cls = RENDERERS[self.renderer_name]
        yield image_cls(id="wc-image")

    def on_mount(self) -> None:
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
        state = "[#4caf50]live[/]" if self.running else "[#ff9800]paused[/]"
        self.query_one("#wc-info", Static).update(
            f"{state}   [#9e9e9e]{self.fps} fps[/]   "
            f"[#9e9e9e]renderer[/] {self.renderer_name}   "
            f"[#9e9e9e]{self.snapshot_url}[/]{extra}"
        )

    async def _tick(self) -> None:
        if not self.running or self._client is None:
            return
        try:
            resp = await self._client.get(self.snapshot_url)
            resp.raise_for_status()
            frame = PILImage.open(io.BytesIO(resp.content))
            frame.load()
            self.query_one("#wc-image").image = frame
            if self._fail_count:
                self._fail_count = 0
                self._update_info()
        except Exception as exc:
            self._fail_count += 1
            # Only surface persistent failures; a dropped frame is not news.
            if self._fail_count in (3, 30):
                self._update_info(
                    f"   [#D41216]{type(exc).__name__}: {exc}[/]"
                )
