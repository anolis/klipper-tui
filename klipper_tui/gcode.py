"""Reading toolpaths out of a gcode file.

Only the layer being looked at is parsed. The file is indexed once to find
where each layer starts, which keeps a large print — tens of megabytes and a
million moves — from having to be held in memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# PrusaSlicer and SuperSlicer mark layers explicitly; Cura numbers them. Where
# neither appears, a Z move on its own is taken to start a layer.
LAYER_CHANGE = re.compile(rb"^;\s*(LAYER_CHANGE|LAYER:\s*-?\d+)")
LAYER_Z = re.compile(rb"^;\s*Z:\s*([0-9.]+)")

MOVE = re.compile(rb"^G[01]\b")
AXIS = {
    b"X": "x", b"Y": "y", b"Z": "z", b"E": "e", b"F": "f",
}


@dataclass
class Layer:
    """Where a layer lives in the file, and how high it is."""
    z: float
    start: int          # byte offset of the layer's first line
    end: int            # byte offset just past its last line
    number: int


@dataclass
class Segment:
    """One straight move on a layer."""
    x0: float
    y0: float
    x1: float
    y1: float
    extruding: bool
    offset: int         # byte offset of the line, for matching print progress


@dataclass
class Toolpath:
    segments: list[Segment] = field(default_factory=list)

    def bounds(self) -> tuple[float, float, float, float] | None:
        drawn = [s for s in self.segments if s.extruding] or self.segments
        if not drawn:
            return None
        xs = [v for s in drawn for v in (s.x0, s.x1)]
        ys = [v for s in drawn for v in (s.y0, s.y1)]
        return min(xs), min(ys), max(xs), max(ys)


def _parse_words(line: bytes) -> dict:
    """Pull the axis words out of a G0/G1 line."""
    values = {}
    for word in line.split():
        if not word:
            continue
        axis = AXIS.get(word[:1].upper())
        if axis is None:
            continue
        try:
            values[axis] = float(word[1:])
        except ValueError:
            continue
    return values


def index_layers(path) -> list[Layer]:
    """Find every layer in the file, in one pass.

    Reads bytes rather than text: the file may contain thumbnails and other
    non-UTF-8 payloads, and byte offsets have to line up with the file position
    Klipper reports.
    """
    layers: list[Layer] = []
    pending_z: float | None = None
    start: int | None = None
    offset = 0
    last_z = 0.0

    with open(path, "rb") as handle:
        for line in handle:
            length = len(line)
            stripped = line.lstrip()

            if stripped.startswith(b";"):
                if LAYER_CHANGE.match(stripped):
                    if start is not None:
                        layers.append(Layer(
                            z=pending_z if pending_z is not None else last_z,
                            start=start, end=offset, number=len(layers)))
                        if pending_z is not None:
                            last_z = pending_z
                    start = offset
                    pending_z = None
                else:
                    found = LAYER_Z.match(stripped)
                    if found:
                        pending_z = float(found.group(1))
            elif start is None and MOVE.match(stripped):
                # No layer markers in this file: begin at the first move and
                # let Z changes below split the layers.
                words = _parse_words(stripped)
                if "z" in words:
                    start = offset
                    pending_z = words["z"]

            offset += length

    if start is not None:
        layers.append(Layer(z=pending_z if pending_z is not None else last_z,
                            start=start, end=offset, number=len(layers)))
    return layers


def index_layers_by_z(path) -> list[Layer]:
    """Fallback for files with no layer comments: split on Z moves."""
    layers: list[Layer] = []
    start: int | None = None
    current_z = None
    offset = 0

    with open(path, "rb") as handle:
        for line in handle:
            length = len(line)
            stripped = line.lstrip()
            if MOVE.match(stripped):
                words = _parse_words(stripped)
                z = words.get("z")
                if z is not None and z != current_z:
                    if start is not None and current_z is not None:
                        layers.append(Layer(z=current_z, start=start,
                                            end=offset, number=len(layers)))
                    start = offset
                    current_z = z
            offset += length

    if start is not None and current_z is not None:
        layers.append(Layer(z=current_z, start=start, end=offset,
                            number=len(layers)))
    return layers


def read_layer(path, layer: Layer, origin: tuple[float, float] | None = None
               ) -> Toolpath:
    """Parse one layer's moves into segments.

    ``origin`` is where the nozzle was when the layer began; without it the
    first move has no start point and is skipped.
    """
    toolpath = Toolpath()
    x, y = (origin or (None, None))
    relative = False
    relative_e = False
    offset = layer.start

    with open(path, "rb") as handle:
        handle.seek(layer.start)
        remaining = layer.end - layer.start
        for line in handle:
            length = len(line)
            if remaining <= 0:
                break
            remaining -= length
            stripped = line.lstrip()

            if stripped.startswith(b"G90"):
                relative = False
            elif stripped.startswith(b"G91"):
                relative = True
            elif stripped.startswith(b"M82"):
                relative_e = False
            elif stripped.startswith(b"M83"):
                relative_e = True
            elif MOVE.match(stripped):
                words = _parse_words(stripped)
                nx = words.get("x")
                ny = words.get("y")
                if relative:
                    nx = (x + nx) if (nx is not None and x is not None) else x
                    ny = (y + ny) if (ny is not None and y is not None) else y
                else:
                    nx = nx if nx is not None else x
                    ny = ny if ny is not None else y

                extrude = words.get("e")
                # With absolute extrusion a retraction also carries an E word,
                # so only a positive relative move counts as laying material.
                extruding = bool(extrude is not None and
                                 (extrude > 0 if relative_e else True))

                if x is not None and y is not None and nx is not None \
                        and ny is not None and (nx != x or ny != y):
                    toolpath.segments.append(
                        Segment(x, y, nx, ny, extruding, offset))
                x, y = nx, ny

            offset += length

    return toolpath


def layer_for_position(layers: list[Layer], file_position: int) -> int | None:
    """Which layer the printer is currently inside."""
    if not layers:
        return None
    for layer in layers:
        if layer.start <= file_position < layer.end:
            return layer.number
    if file_position >= layers[-1].end:
        return layers[-1].number
    return 0
