"""Draw the temperature plot as pixels rather than braille dots.

Braille gives a cell 2x4 subpixels, which is four times what block characters
manage and is why the chart is drawn that way by default. It is still eight
dots per character, though: on a 70x16 plot that is 140x64 points for ten
minutes of two traces, so a slow drift and a fast wobble look much alike.

Where the terminal can display an image — kitty and ghostty through the
graphics protocol, or a sixel terminal — the same plot can be drawn at the
terminal's own pixel resolution instead, which is roughly ten times as many
points in each direction, with anti-aliased lines.

Only the plot area becomes an image. The axis labels stay as text so they are
rendered by the terminal's own font at its own hinting, rather than by a
bitmap font baked into a picture.
"""

from __future__ import annotations

import os

from typing import Iterable, Sequence

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - Pillow is a hard dependency
    Image = None
    ImageDraw = None


# A terminal cell if we cannot measure one. Roughly what a 14px font gives.
FALLBACK_CELL = (9, 19)

# Keep a redraw well inside a frame even on a large panel.
MAX_PIXELS = 1600 * 900


def graphics_available(renderer: str = "auto") -> bool:
    """Can this terminal show an actual image?

    Half-block and unicode renderers do not count: they are coarser than the
    braille chart they would be replacing, so falling back to them would make
    the plot worse rather than better.

    Detection is not done here. textual-image queries the terminal once, when
    textual_image.renderable is first imported, and binds the answer to the
    renderable it exports. Its own query cannot be repeated later:

        "this function will not work anymore once Textual is started.
         Textual runs a thread to read stdin and will grab the response"

    Asking again from inside a running app therefore always answers no, which
    is exactly what this did when it first shipped. Read what the library
    already decided instead.
    """
    forced = os.environ.get("KLIPPER_TUI_GRAPH_HIRES", "").strip().lower()
    if forced in ("0", "false", "no"):
        return False
    if forced in ("1", "true", "yes"):
        return True

    # An explicit --render choice governs the graph as well as the webcam.
    if renderer in ("sixel", "tgp"):
        return True
    if renderer in ("halfcell", "unicode"):
        return False

    if Image is None:
        return False
    try:
        from textual_image.renderable import Image as Resolved
        from textual_image.renderable import SixelImage, TGPImage
    except ImportError:
        return False
    return Resolved in (SixelImage, TGPImage)


def renderer_name() -> str:
    """Which renderer textual-image settled on, for diagnosing a fallback."""
    try:
        from textual_image.renderable import Image as Resolved
        return Resolved.__module__.rsplit(".", 1)[-1]
    except Exception:
        return "unknown"


# Enough of the palette to draw with if the theme cannot be read yet.
FALLBACK_COLOURS = {
    "hot": "#d1553d", "hot-dim": "#6b2c20",
    "bed": "#7b6f9c", "bed-dim": "#3d3652",
    "vol-frame": "#a32638", "vol-floor": "#5c4a52",
    "vol-head": "#e0a13c", "vol-drop": "#c4485a",
    "surface": "#141011", "background": "#0b0809",
    "panel": "#1c1618", "panel-lighten-1": "#2b2527",
    "foreground": "#ddcfd2", "text-muted": "#9e8d91",
}


def resolve(app, token: str, fallback: str = "#ffffff") -> str:
    """A theme token like "$hot" as a concrete colour Pillow will accept.

    Textual resolves these itself when it renders markup, but Pillow has never
    heard of them, so anything drawn into an image has to look them up first.
    """
    name = token.lstrip("$")
    try:
        value = (app.theme_variables or {}).get(name)
        if isinstance(value, str) and value.startswith("#"):
            return value
    except Exception:
        pass
    try:
        value = getattr(app.current_theme, name.replace("-", "_"), None)
        if isinstance(value, str) and value.startswith("#"):
            return value
    except Exception:
        pass
    return FALLBACK_COLOURS.get(name, fallback)


def marker_arm(canvas) -> int:
    """Half-length of the nozzle cross, in subpixels of whatever canvas.

    Five subpixels reads well on braille's 160-wide grid and disappears on a
    1600-pixel one, so scale it instead of hardcoding it.
    """
    return max(2, canvas.sub_width // 110)


def cell_size() -> tuple[int, int]:
    try:
        from textual_image._terminal import get_cell_size
        size = get_cell_size()
        width, height = int(size.width), int(size.height)
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return FALLBACK_CELL


def plot_size(cols: int, rows: int) -> tuple[int, int]:
    """Pixel size for a plot that has to sit in cols x rows character cells."""
    cell_w, cell_h = cell_size()
    width = max(16, cols * cell_w)
    height = max(16, rows * cell_h)
    # A very wide panel on a hidpi terminal can ask for more pixels than is
    # worth drawing at a frame a second; scale the pair down together.
    excess = (width * height) / MAX_PIXELS
    if excess > 1:
        shrink = excess ** 0.5
        width, height = int(width / shrink), int(height / shrink)
    return width, height


def _points(data: Sequence[float], lo: float, hi: float,
            width: int, height: int) -> list[tuple[float, float]]:
    span = (hi - lo) or 1.0
    count = len(data)
    if count < 2:
        return []
    step = (width - 1) / (count - 1)
    return [(i * step, (hi - value) / span * (height - 1))
            for i, value in enumerate(data)]


def render(series: Iterable[tuple[Sequence[float], str]],
           lo: float, hi: float, width: int, height: int,
           background: str, grid: str | None = None):
    """One image of the plot area. Series are drawn in the order given.

    Each series is (samples, colour). Colours are anything Pillow accepts,
    which includes the "#rrggbb" the themes already use.
    """
    if Image is None:
        return None

    # Draw at twice the size and shrink, which is cheaper than a real
    # anti-aliasing pass and enough to take the stairs off a diagonal.
    scale = 2
    canvas = Image.new("RGB", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(canvas)

    if grid:
        for fraction in (0.25, 0.5, 0.75):
            y = fraction * (height * scale - 1)
            draw.line([(0, y), (width * scale, y)], fill=grid, width=1)

    for data, colour in series:
        points = _points(data, lo, hi, width * scale, height * scale)
        if len(points) >= 2:
            draw.line(points, fill=colour, width=scale + 1, joint="curve")

    return canvas.resize((width, height), Image.LANCZOS)


class PixelCanvas:
    """A drawing surface with BrailleCanvas's interface, backed by real pixels.

    The panels that draw the toolpath and the build volume already work in
    "subpixels" — braille's 2x4 grid per cell. Handing them one of these
    instead makes every subpixel an actual pixel, so the projection maths, the
    framing and the draw order all carry over untouched and only the output
    differs.

    Colours arrive as theme tokens like "$hot", because that is what the
    braille renderer needs. A resolver turns them into something Pillow will
    take, and the answers are cached: a frame asks for the same handful of
    colours thousands of times.
    """

    def __init__(self, width: int, height: int, background: str,
                 resolve, stroke: int = 2, cells: tuple[int, int] | None = None
                 ) -> None:
        # Both canvases mean the same thing by these: width and height count
        # character cells, sub_width and sub_height count the units drawing
        # happens in. Braille has 2x4 of the latter per cell; here they are
        # pixels. Keeping the names honest is the whole point of the class.
        self.sub_width = width
        self.sub_height = height
        self.width, self.height = cells or (width, height)
        self.stroke = max(1, stroke)
        self._resolve = resolve
        self._cache: dict[str, object] = {}
        self._image = Image.new("RGB", (width, height), background)
        self._draw = ImageDraw.Draw(self._image)

    def _colour(self, token: str):
        cached = self._cache.get(token)
        if cached is None:
            cached = self._resolve(token)
            self._cache[token] = cached
        return cached

    def set(self, sx: int, sy: int, color: str) -> None:
        if not (0 <= sx < self.sub_width and 0 <= sy < self.sub_height):
            return
        half = self.stroke // 2
        self._draw.rectangle(
            [sx - half, sy - half, sx - half + self.stroke - 1,
             sy - half + self.stroke - 1],
            fill=self._colour(color))

    def line(self, sx0: int, sy0: int, sx1: int, sy1: int,
             color: str) -> None:
        self._draw.line([(sx0, sy0), (sx1, sy1)], fill=self._colour(color),
                        width=self.stroke)

    @property
    def image(self):
        return self._image
