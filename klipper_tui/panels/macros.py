"""Buttons for the printer's own macros.

Everyone's config has macros, and without this the only way to reach them is
to type their name into the console.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

# Klipper's own plumbing, and the ones already driven by the job controls.
# Offering these as buttons would be noise at best and confusing at worst.
HIDDEN = {
    "PAUSE", "RESUME", "CANCEL_PRINT",
    "_CLIENT_LINEAR_MOVE", "_CLIENT_RETRACT", "_CLIENT_EXTRUDE",
    "_TOOLHEAD_PARK_PAUSE_CANCEL",
}


def is_hidden(name: str) -> bool:
    # A leading underscore is the convention for a macro meant to be called by
    # other macros rather than by a person.
    return name.startswith("_") or name.upper() in HIDDEN


def macro_names(status: dict) -> list[str]:
    found = []
    for key in status:
        if key.startswith("gcode_macro "):
            name = key.removeprefix("gcode_macro ")
            if not is_hidden(name):
                found.append(name)
    return sorted(found)


class MacrosPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="macros-panel", classes="panel")
        self.macros: list[str] = []
        self._drawn = False

    def compose(self) -> ComposeResult:
        yield Label("Macros", classes="panel-title")
        yield Static("", id="mac-empty", classes="dim")
        yield Vertical(id="mac-list")

    def update_status(self, status: dict) -> None:
        found = macro_names(status)
        # "No change" is not the same as "never drawn": a printer with no
        # macros at all matches the initial empty list, and without this the
        # panel would stay blank rather than saying so.
        if found == self.macros and self._drawn:
            return
        self.macros = found
        self._drawn = True
        self._rebuild()

    def _rebuild(self) -> None:
        try:
            container = self.query_one("#mac-list", Vertical)
            empty = self.query_one("#mac-empty", Static)
        except Exception:
            return
        container.remove_children()
        if not self.macros:
            empty.update(
                "[$text-muted]No macros defined, beyond the ones the job "
                "controls already use.[/]"
            )
            return
        empty.update("")

        # A handful per row, so a config with dozens stays readable.
        rows, row = [], []
        for index, name in enumerate(self.macros):
            row.append(Button(name, id=f"mac-run-{index}"))
            if len(row) == 3:
                rows.append(Horizontal(*row, classes="btn-row compact-row"))
                row = []
        if row:
            rows.append(Horizontal(*row, classes="btn-row compact-row"))
        container.mount(*rows)

    def macro_at(self, index: int) -> str | None:
        return self.macros[index] if 0 <= index < len(self.macros) else None
