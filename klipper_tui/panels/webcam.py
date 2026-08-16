"""Webcam panel.

Frames come from the camera's MJPEG stream, which pushes continuously, rather
than from one HTTP request per frame. Rendering goes through textual-image,
which can emit the Kitty graphics protocol or sixel where the terminal supports
them and falls back to unicode blocks where it does not.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import time

import httpx
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

# Image rendering is a required dependency, but a broken or unbuildable Pillow
# should cost the camera tab rather than the whole application.
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

FPS_CHOICES = [1, 5, 10, 15, 30]

# JPEG start and end markers. Framing on these is simpler than parsing the
# multipart boundary and works across streamer implementations.
JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"

# Guard against a response that never yields a complete frame.
MAX_BUFFER = 8 * 1024 * 1024


def stream_url_for(snapshot_url: str) -> str:
    """The streaming form of a snapshot URL, by convention."""
    if "action=snapshot" in snapshot_url:
        return snapshot_url.replace("action=snapshot", "action=stream")
    if snapshot_url.endswith("/snapshot"):
        return snapshot_url[: -len("/snapshot")] + "/stream"
    return snapshot_url


class WebcamPanel(Vertical):
    def __init__(self, snapshot_url: str, renderer: str = "auto") -> None:
        super().__init__(id="webcam-panel")
        self.snapshot_url = snapshot_url
        self.stream_url = stream_url_for(snapshot_url)
        self.renderer_name = renderer if renderer in RENDERERS else "auto"
        self.fps = 15
        self.running = True
        self.streaming = False
        self.measured_fps = 0.0

        self._client: httpx.AsyncClient | None = None
        self._frames_task: asyncio.Task | None = None
        self._aspect: float | None = None
        self._last_shown = 0.0
        self._frame_times: list[float] = []
        self._status_note = ""
        # Streaming stops while the panel is off screen. A 720p feed is the
        # heaviest thing here, and pulling it for a tab nobody is looking at
        # starves everything else — the gcode download most visibly.
        self._visible = True

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
                "[$warning]Image rendering is unavailable.[/]\n\n"
                "[$text-muted]textual-image or Pillow failed to import, which "
                "usually means the install is incomplete. Reinstalling should "
                "fix it:[/]\n"
                "    pip install --force-reinstall klipper-tui",
                id="wc-missing",
            )

    def on_mount(self) -> None:
        if not AVAILABLE:
            self.query_one("#wc-info", Static).update(
                "[$text-muted]image rendering unavailable[/]"
            )
            return
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))
        self._update_info()
        self._start()

    async def on_unmount(self) -> None:
        task, self._frames_task = self._frames_task, None
        if task and not task.done():
            task.cancel()
            # Await the cancellation so it settles here rather than surfacing
            # as an unhandled error while the app tears down.
            with contextlib.suppress(BaseException):
                await task
        if self._client:
            with contextlib.suppress(Exception):
                await self._client.aclose()

    # -- control ---------------------------------------------------------------

    def _start(self) -> None:
        if not (self.running and self._visible):
            return
        if self._frames_task is None or self._frames_task.done():
            self._frames_task = asyncio.create_task(self._run())

    def on_show(self) -> None:
        self._visible = True
        if AVAILABLE and self.running:
            self._start()
            self._safe_update_info()

    def on_hide(self) -> None:
        self._visible = False
        self._stop()
        self.streaming = False
        self.measured_fps = 0.0

    def _stop(self) -> None:
        task, self._frames_task = self._frames_task, None
        if task and not task.done():
            task.cancel()

    def set_url(self, url: str) -> None:
        self.snapshot_url = url
        self.stream_url = stream_url_for(url)
        if not AVAILABLE:
            return
        self._stop()
        self._update_info()
        if self.running:
            self._start()

    def set_fps(self, fps: int) -> None:
        self.fps = fps
        self._update_info()

    def toggle(self) -> bool:
        self.running = not self.running
        if not AVAILABLE:
            return self.running
        if self.running:
            self._start()
        else:
            self._stop()
            self.streaming = False
        self._update_info()
        return self.running

    def _update_info(self, extra: str = "") -> None:
        if not self._visible:
            state = "[$text-muted]idle while hidden[/]"
        else:
            state = "[$success]live[/]" if self.running else "[$warning]paused[/]"
        mode = "stream" if self.streaming else "snapshots"
        rate = f"{self.measured_fps:.1f}" if self.measured_fps else "--"
        self.query_one("#wc-info", Static).update(
            f"{state}   [$text-muted]{rate} fps of {self.fps} max[/]   "
            f"[$text-muted]{mode}[/]   "
            f"[$text-muted]renderer[/] {self.renderer_name}"
            f"{extra or self._status_note}"
        )

    # -- frame sources ---------------------------------------------------------

    async def _run(self) -> None:
        """Prefer the continuous stream; fall back to polling snapshots."""
        while self.running and self._visible:
            try:
                await self._consume_stream()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.streaming = False
                self._status_note = (
                    f"   [$warning]stream unavailable ({type(exc).__name__}), "
                    f"using snapshots[/]"
                )
                try:
                    await self._poll_snapshots()
                except asyncio.CancelledError:
                    raise
                except Exception as poll_exc:
                    self._status_note = (
                        f"   [$error]{type(poll_exc).__name__}: {poll_exc}[/]"
                    )
                    self._safe_update_info()
                    await asyncio.sleep(3.0)

    async def _consume_stream(self) -> None:
        assert self._client is not None
        async with self._client.stream("GET", self.stream_url) as response:
            response.raise_for_status()
            self.streaming = True
            self._status_note = ""
            buffer = bytearray()
            async for chunk in response.aiter_bytes():
                if not (self.running and self._visible):
                    return
                buffer += chunk
                if len(buffer) > MAX_BUFFER:
                    del buffer[:-MAX_BUFFER // 2]
                while True:
                    start = buffer.find(JPEG_START)
                    if start < 0:
                        break
                    end = buffer.find(JPEG_END, start + 2)
                    if end < 0:
                        break
                    frame = bytes(buffer[start:end + 2])
                    del buffer[:end + 2]
                    self._show(frame)

    async def _poll_snapshots(self) -> None:
        assert self._client is not None
        while self.running and self._visible:
            response = await self._client.get(self.snapshot_url)
            response.raise_for_status()
            self._show(response.content, throttled=False)
            await asyncio.sleep(1 / max(1, self.fps))

    # -- display ---------------------------------------------------------------

    def _show(self, jpeg: bytes, throttled: bool = True) -> None:
        """Decode and display a frame, dropping any beyond the target rate."""
        now = time.monotonic()
        if throttled and now - self._last_shown < 1 / max(1, self.fps):
            return  # arrived faster than asked for; skip without decoding
        self._last_shown = now

        try:
            frame = PILImage.open(io.BytesIO(jpeg))
            frame.load()
        except Exception:
            return  # a partial or corrupt frame is not worth reporting

        if frame.height:
            self._fit(frame.width / frame.height)
        try:
            self.query_one("#wc-image").image = frame
        except Exception:
            return

        self._frame_times.append(now)
        cutoff = now - 3.0
        self._frame_times = [t for t in self._frame_times if t >= cutoff]
        if len(self._frame_times) > 1:
            span = self._frame_times[-1] - self._frame_times[0]
            self.measured_fps = (len(self._frame_times) - 1) / span if span else 0.0
        self._safe_update_info()

    def _safe_update_info(self) -> None:
        try:
            self._update_info()
        except Exception:
            pass

    def _fit(self, aspect: float) -> None:
        """Size the image widget so the frame keeps its shape.

        A terminal cell is roughly twice as tall as it is wide, so the cell
        counts must be divided by that ratio to get the displayed shape.
        """
        if aspect <= 0 or aspect == self._aspect:
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
