"""Modal asking which temperature to preheat to before moving filament."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from .temperature import PRESETS


class PreheatScreen(ModalScreen[float | None]):
    """Returns the chosen hotend temperature, or None if cancelled."""

    BINDINGS = [("escape", "dismiss_none", "Cancel")]

    def __init__(self, action: str, current: float | None) -> None:
        super().__init__()
        self.action = action
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="preheat-box"):
            yield Label("Hotend is too cold", classes="panel-title")
            now = f"{self.current:.1f}°C" if self.current is not None else "--"
            yield Static(
                f"[$text-muted]{self.action} needs the nozzle at 170°C or above. "
                f"Currently [/][b]{now}[/b][$text-muted]. "
                f"Pick a temperature and it will heat, wait, then continue.[/]"
            )
            with Horizontal(classes="btn-row compact-row"):
                for name, (hot, _) in PRESETS.items():
                    yield Button(f"{name} {hot}°", id=f"ph-preset-{name}")
            with Horizontal(classes="btn-row"):
                yield Input(placeholder="custom °C", id="ph-custom",
                            type="integer")
                yield Button("Heat", id="ph-go", classes="-primary")
                yield Button("Cancel", id="ph-cancel", classes="-danger")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "ph-cancel":
            self.dismiss(None)
        elif bid == "ph-go":
            raw = self.query_one("#ph-custom", Input).value.strip()
            try:
                self.dismiss(float(raw))
            except ValueError:
                self.notify("Enter a temperature first", severity="warning")
        elif bid.startswith("ph-preset-"):
            name = bid.removeprefix("ph-preset-")
            self.dismiss(float(PRESETS[name][0]))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.dismiss(float(event.value))
        except ValueError:
            self.notify("Enter a temperature first", severity="warning")
