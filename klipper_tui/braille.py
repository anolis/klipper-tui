"""Braille-cell line plotting.

Each terminal cell holds a 2x4 grid of braille dots, so a chart drawn this way
has four times the vertical resolution of one built from block characters.
A cell can only carry one colour, so overlapping series are resolved by the
order they are drawn — later series win.
"""

from __future__ import annotations

# Bit for each (column, row) position inside a braille cell.
DOTS = (
    (0x01, 0x02, 0x04, 0x40),  # left column, rows top->bottom
    (0x08, 0x10, 0x20, 0x80),  # right column
)

BRAILLE_BASE = 0x2800


class BrailleCanvas:
    """A width x height grid of terminal cells addressed in braille subpixels."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.sub_width = width * 2
        self.sub_height = height * 4
        # (cell_x, cell_y) -> [dot mask, colour]
        self._cells: dict[tuple[int, int], list] = {}

    def set(self, sx: int, sy: int, color: str) -> None:
        """Light the subpixel at (sx, sy), origin top-left."""
        if not (0 <= sx < self.sub_width and 0 <= sy < self.sub_height):
            return
        cx, cy = sx // 2, sy // 4
        bit = DOTS[sx % 2][sy % 4]
        cell = self._cells.get((cx, cy))
        if cell is None:
            self._cells[(cx, cy)] = [bit, color]
        else:
            cell[0] |= bit
            cell[1] = color

    def line(self, sx0: int, sy0: int, sx1: int, sy1: int, color: str) -> None:
        """Bresenham line, so steep temperature ramps stay connected."""
        dx = abs(sx1 - sx0)
        dy = -abs(sy1 - sy0)
        step_x = 1 if sx0 < sx1 else -1
        step_y = 1 if sy0 < sy1 else -1
        err = dx + dy
        while True:
            self.set(sx0, sy0, color)
            if sx0 == sx1 and sy0 == sy1:
                return
            err2 = 2 * err
            if err2 >= dy:
                err += dy
                sx0 += step_x
            if err2 <= dx:
                err += dx
                sy0 += step_y

    def render(self) -> list[str]:
        """Render to one markup string per row, merging runs of equal colour."""
        rows = []
        for cy in range(self.height):
            parts: list[str] = []
            run_color: str | None = None
            run_chars: list[str] = []

            def flush() -> None:
                if not run_chars:
                    return
                text = "".join(run_chars)
                parts.append(f"[{run_color}]{text}[/]" if run_color else text)

            for cx in range(self.width):
                cell = self._cells.get((cx, cy))
                if cell is None:
                    char, color = " ", None
                else:
                    char, color = chr(BRAILLE_BASE + cell[0]), cell[1]
                if color != run_color:
                    flush()
                    run_chars = []
                    run_color = color
                run_chars.append(char)
            flush()
            rows.append("".join(parts))
        return rows
