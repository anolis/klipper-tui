"""The two canvases must be interchangeable, and the panels must use both.

PixelCanvas exists so the toolpath and the build volume can be drawn with the
projections they already had, by swapping the surface underneath them. That
only works while the surface really does offer what BrailleCanvas offers —
and it shipped without .width and .height, which crashed the 3D view the
moment a model was loaded. Nothing caught it because the panel was only ever
exercised with an empty model.
"""

import asyncio
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())

from textual.app import App, ComposeResult

from klipper_tui import pixelgraph
from klipper_tui.braille import BrailleCanvas
from klipper_tui.gcode import Segment, Toolpath
from klipper_tui.panels.gcodeview import GcodeViewPanel
from klipper_tui.panels.position import PositionPanel
from klipper_tui.pixelgraph import PixelCanvas
from klipper_tui.theming import DEFAULT_THEME, register

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


# -- the surfaces agree --------------------------------------------------------

braille = BrailleCanvas(40, 10)
pixels = PixelCanvas(400, 200, "#000000", lambda token: "#ffffff",
                     cells=(40, 10))

expected = {n for n in dir(braille) if not n.startswith("_")} - {"render"}
missing = sorted(expected - {n for n in dir(pixels) if not n.startswith("_")})
if missing:
    failures.append(f"PixelCanvas is missing {missing}")

# width and height count cells on both; sub_* count drawing units on both.
check("braille cells", (braille.width, braille.height), (40, 10))
check("pixel cells", (pixels.width, pixels.height), (40, 10))
check("braille units", (braille.sub_width, braille.sub_height), (80, 40))
check("pixel units", (pixels.sub_width, pixels.sub_height), (400, 200))

# Drawing off the edge is ignored rather than raising, on both.
for canvas in (braille, pixels):
    name = type(canvas).__name__
    try:
        canvas.set(-5, -5, "$hot")
        canvas.set(10_000, 10_000, "$hot")
        canvas.line(-20, -20, 10_000, 10_000, "$hot")
    except Exception as error:
        failures.append(f"{name} raised while drawing out of bounds: {error!r}")


# -- the panels draw, with content, in both modes ------------------------------

def a_layer(points=400):
    segments, prev = [], None
    for i in range(points):
        t = i / points * math.tau * 5
        p = (120 + 50 * math.cos(t), 120 + 50 * math.sin(t))
        if prev:
            segments.append(Segment(prev[0], prev[1], p[0], p[1], True, i * 40))
        prev = p
    return Toolpath(segments)


def a_model(points=600):
    # What record_motion accumulates: quantised (x, y, z) voxels.
    return {(i % 40, (i * 7) % 40, i % 20) for i in range(points)}


class Harness(App):
    CSS_PATH = str(Path(__file__).resolve().parent.parent
                   / "klipper_tui" / "app.tcss")

    def __init__(self, hires: bool) -> None:
        super().__init__()
        self.hires = hires

    def compose(self) -> ComposeResult:
        renderer = "tgp" if self.hires else "halfcell"
        yield GcodeViewPanel(renderer=renderer)
        yield PositionPanel(renderer=renderer)

    def on_mount(self) -> None:
        register(self)
        self.theme = DEFAULT_THEME


async def exercise(hires: bool) -> None:
    app = Harness(hires)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        view = app.query_one(GcodeViewPanel)
        pos = app.query_one(PositionPanel)
        check(f"toolpath hires={hires}", view.hires, hires)
        check(f"position hires={hires}", pos.hires, hires)

        view.toolpath = a_layer()
        view.frame = view.toolpath.bounds()
        view.file_position = 8000
        view.head = (120.0, 120.0)
        view._cache_key = None

        pos.model = a_model()
        pos.show_model = True

        for spinning in (False, True):
            pos.spinning = spinning
            for panel in (view, pos):
                try:
                    panel._redraw()
                except Exception as error:
                    failures.append(
                        f"{type(panel).__name__} hires={hires} "
                        f"spinning={spinning}: {error!r}")
            await pilot.pause()

        # Spinning must actually cost a quarter of the pixels, and the model
        # cache must not be reused across the two resolutions.
        if hires and pos._image_widget is not None:
            pos.spinning = False
            pos._redraw()
            still = pos._image_widget.image
            pos.spinning = True
            pos._redraw()
            spun = pos._image_widget.image
            if still and spun:
                ratio = ((still.size[0] * still.size[1])
                         / max(1, spun.size[0] * spun.size[1]))
                if not 3.5 < ratio < 4.5:
                    failures.append(
                        f"spinning uses 1/{ratio:.1f} of the pixels, wanted 1/4")


asyncio.run(exercise(False))
asyncio.run(exercise(True))

if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
