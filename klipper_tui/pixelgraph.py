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
