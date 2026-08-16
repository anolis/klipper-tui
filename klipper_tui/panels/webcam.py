"""Webcam panel.

Frames come from the camera's MJPEG stream, which pushes continuously, rather
than from one HTTP request per frame. Rendering goes through textual-image,
which can emit the Kitty graphics protocol or sixel where the terminal supports
them and falls back to unicode blocks where it does not.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import os
import time

import httpx
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from ..visibility import on_screen

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

    def _use_fast_png() -> None:
        """Encode PNGs for speed rather than size.

        The renderer hands each frame to Pillow's PNG writer, which defaults to
        compression level 6 — around 140ms for a single 800x450 frame, so a few
        frames a second saturate a core. Level 1 costs about 36ms for a file
        under 10% larger, and the frame is thrown away as soon as it is drawn.
        """
        from PIL import PngImagePlugin

        if getattr(PngImagePlugin, "_klipper_tui_fast", False):
            return
        original = PngImagePlugin._save

        def save(image, fp, filename, *args, **kwargs):
            # Pass the rest through untouched: PIL's own defaults for these
            # are not None, and overriding them breaks the writer.
            image.encoderinfo.setdefault("compress_level", 1)
            return original(image, fp, filename, *args, **kwargs)

        PngImagePlugin._save = save
        # The save registry holds a direct reference to the original, so
        # replacing the module attribute alone changes nothing.
        PILImage.register_save("PNG", save)
        PngImagePlugin._klipper_tui_fast = True

    def _use_raw_tgp() -> None:
        """Hand kitty raw pixels instead of a PNG.

        The kitty graphics protocol takes uncompressed RGB (f=24) as happily as
        it takes a PNG, and skipping the encoder is the difference between 38ms
        and 2ms for a 800x450 frame — most of what the camera costs.

        The tradeoff is size: base64 raw is around 1.4MB a frame against 600KB
        for a PNG, which is nothing down a pipe to a local terminal but rude
        over a slow ssh session. So this stays off when the session is remote,
        and KLIPPER_TUI_RAW_TGP forces it either way.
        """
        forced = os.environ.get("KLIPPER_TUI_RAW_TGP", "").strip().lower()
        if forced in ("0", "false", "no"):
            return
        remote = bool(os.environ.get("SSH_CONNECTION") or
                      os.environ.get("SSH_CLIENT"))
        if remote and forced not in ("1", "true", "yes"):
            return

        from textual_image.renderable import tgp

        if getattr(tgp, "_klipper_tui_raw", False):
            return

        def send(self, width: int, height: int) -> None:
            self.terminal_image_id = next(tgp.Image._image_id_counter)
            frame = self._image_data.scaled(width, height).pil_image
            if frame.mode != "RGB":
                frame = frame.convert("RGB")
            data = base64.standard_b64encode(frame.tobytes()).decode("ascii")
            # Only the first chunk carries the format and the pixel
            # dimensions; the rest are continuations.
            head: dict = {"f": 24, "s": frame.width, "v": frame.height, "q": 2}
            while data:
                chunk, data = data[:4096], data[4096:]
                tgp._send_tgp_message(
                    i=self.terminal_image_id,
                    m=1 if data else 0,
                    payload=chunk,
                    **head,
                )
                head = {}

        tgp.Image._send_image_to_terminal = send
        tgp._klipper_tui_raw = True

    _use_fast_png()
    try:
        _use_raw_tgp()
    except Exception:
        # An upstream rename costs the speedup, not the camera.
        pass

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

# Rough pixels per terminal cell, used to decide how far a frame can be scaled
# down before it is handed to the renderer. Generous on purpose: too small
# looks soft, too large is wasted work.
CELL_PIXELS_W = 8
CELL_PIXELS_H = 16


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
        # Each frame costs roughly 30-40ms to scale and encode for the
        # terminal, so 15 was never actually reachable — it just pinned a core
        # trying. Five is smooth enough to watch a print and leaves the rest of
        # the interface responsive; the buttons go higher if you want.
        self.fps = 5
        self.running = True
        self.streaming = False
        self.measured_fps = 0.0

        self._client: httpx.AsyncClient | None = None
        self._frames_task: asyncio.Task | None = None
        self._fitted: tuple[float, int, int] | None = None
        self._last_shown = 0.0
        self._frame_times: list[float] = []
        self._status_note = ""
        # Streaming stops while the panel is off screen. A 720p feed is the
        # heaviest thing here, and pulling it for a tab nobody is looking at
        # starves everything else — the gcode download most visibly.
        self._visible = False

    def compose(self) -> ComposeResult:
        yield Label("Webcam", classes="panel-title")

        with Horizontal(classes="btn-row compact-row"):
            yield Button("Pause", id="wc-toggle", classes="-primary")
            # Short labels: "30 fps" pushed the row past an 80-column panel.
            for fps in FPS_CHOICES:
                yield Button(f"{fps}", id=f"wc-fps-{fps}")

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
        # Show and Hide alone miss a tab that has never been opened, so the
        # stream is reconciled against what is really on screen.
        self.set_interval(1.0, self._check_visibility)
        self._check_visibility()

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

    def _check_visibility(self) -> None:
        visible = on_screen(self)
        if visible == self._visible:
            return
        self._visible = visible
        if visible:
            if AVAILABLE and self.running:
                self._start()
        else:
            self._stop()
            self.streaming = False
            self.measured_fps = 0.0
        self._safe_update_info()

    def on_show(self) -> None:
        self._check_visibility()

    def on_hide(self) -> None:
        self._check_visibility()

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
        frame = self._scaled(frame)
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

    def _scaled(self, frame):
        """Shrink a frame to about what the widget can actually show.

        A 720p frame drawn into a widget a few hundred pixels wide is mostly
        wasted: every one of those pixels is encoded and written to the
        terminal each time. Scaling first is far cheaper and looks the same.
        """
        try:
            image = self.query_one("#wc-image")
            cells_w, cells_h = image.size.width, image.size.height
        except Exception:
            return frame
        if cells_w < 2 or cells_h < 2:
            return frame

        target_w = cells_w * CELL_PIXELS_W
        target_h = cells_h * CELL_PIXELS_H
        if frame.width <= target_w and frame.height <= target_h:
            return frame
        scale = min(target_w / frame.width, target_h / frame.height)
        size = (max(1, int(frame.width * scale)),
                max(1, int(frame.height * scale)))
        try:
            return frame.resize(size, PILImage.BILINEAR)
        except Exception:
            return frame

    def _safe_update_info(self) -> None:
        try:
            self._update_info()
        except Exception:
            pass

    def _fit(self, aspect: float) -> None:
        """Size the image widget so the frame keeps its shape.

        A terminal cell is roughly twice as tall as it is wide, so the cell
        counts must be divided by that ratio to get the displayed shape.

        Recomputed whenever the space available changes, not only when the
        aspect does: a widget left at its old size while the panel resizes
        leaves the terminal scaling the picture, which looks soft.
        """
        if aspect <= 0:
            return
        image = self.query_one("#wc-image")
        avail_w = self.size.width - 4    # panel padding plus image border
        avail_h = self.size.height - 8   # title, controls, info, border
        if avail_w < 4 or avail_h < 3:
            return
        if self._fitted == (aspect, avail_w, avail_h):
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
        self._fitted = (aspect, avail_w, avail_h)
