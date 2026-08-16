"""The pixel plot renderer, without a terminal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui import pixelgraph

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


if pixelgraph.Image is None:
    print("skipped: Pillow unavailable")
    sys.exit(0)

# -- sizing --------------------------------------------------------------------

cell_w, cell_h = pixelgraph.cell_size()
if cell_w <= 0 or cell_h <= 0:
    failures.append(f"cell size is not positive: {(cell_w, cell_h)}")

width, height = pixelgraph.plot_size(70, 16)
check("plot width follows the cell", width, 70 * cell_w)
check("plot height follows the cell", height, 16 * cell_h)

# A tiny panel must still produce a drawable image rather than a 0x0 one.
tiny_w, tiny_h = pixelgraph.plot_size(1, 1)
if tiny_w < 16 or tiny_h < 16:
    failures.append(f"tiny plot collapsed to {(tiny_w, tiny_h)}")

# An absurd panel is capped, and capped in proportion.
huge_w, huge_h = pixelgraph.plot_size(2000, 600)
if huge_w * huge_h > pixelgraph.MAX_PIXELS * 1.02:
    failures.append(f"huge plot not capped: {huge_w * huge_h} pixels")
ratio_before = (2000 * cell_w) / (600 * cell_h)
ratio_after = huge_w / huge_h
if abs(ratio_before - ratio_after) > 0.05 * ratio_before:
    failures.append("capping changed the aspect ratio")

# -- drawing -------------------------------------------------------------------

hot = [200 + i % 20 for i in range(600)]
bed = [60] * 600
image = pixelgraph.render([(bed, "#7b6f9c"), (hot, "#d1553d")],
                          40, 230, 400, 200, "#141011", "#2a2226")
check("image size", image.size, (400, 200))
check("image mode", image.mode, "RGB")

# The image is supersampled and shrunk, so a trace lands as a band of blended
# pixels rather than its exact colour. Ask which pixels are nearer to each
# trace than to the background instead.
def nearest(pixel, palette):
    return min(palette, key=lambda c: sum((a - b) ** 2
                                          for a, b in zip(pixel, c)))


PALETTE = {
    "background": (20, 16, 17),
    "hotend": (209, 85, 61),
    "bed": (123, 111, 156),
}
tally = {name: 0 for name in PALETTE}
for count, pixel in image.getcolors(maxcolors=1000000):
    for name, colour in PALETTE.items():
        if nearest(pixel, list(PALETTE.values())) == colour:
            tally[name] += count
            break

for name in ("hotend", "bed"):
    if tally[name] < 100:
        failures.append(f"the {name} trace covers only {tally[name]} pixels")
if tally["background"] < 400 * 200 * 0.5:
    failures.append("the background is mostly missing")

# Too few samples to draw a line must not raise.
pixelgraph.render([([215], "#d1553d")], 0, 300, 80, 40, "#000000")
pixelgraph.render([([], "#d1553d")], 0, 300, 80, 40, "#000000")

# A flat series still has to land inside the image.
flat = pixelgraph.render([([100] * 50, "#ffffff")], 0, 200, 60, 30, "#000000")
brightest = max(sum(p) for _, p in flat.getcolors(maxcolors=100000))
if brightest < 400:
    failures.append(f"flat series barely drawn (brightest pixel {brightest})")

# lo == hi must not divide by zero.
pixelgraph.render([([100] * 10, "#ffffff")], 100, 100, 60, 30, "#000000")

if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
