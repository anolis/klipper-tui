"""Shown while Moonraker or Klipper is unreachable."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

# Klippy states that mean the printer is not usable, with what to say about it.
STATE_HELP = {
    "shutdown": (
        "Klipper has shut down. This usually follows an error — check the "
        "console for the reason, then use Firmware Restart."
    ),
    "error": (
        "Klipper reported an error and stopped. Check the console, fix the "
        "cause, then use Firmware Restart."
    ),
    "startup": "Klipper is starting up.",
    "disconnected": "Moonraker is running but cannot reach Klipper.",
}


class OfflineScreen(ModalScreen[str | None]):
    """Blocks the UI while offline. Returns an action id, or None if dismissed."""

    BINDINGS = [("escape", "dismiss_none", "Dismiss")]

    def __init__(self, connected: bool, klippy_state: str, target: str) -> None:
        super().__init__()
        self.connected = connected
        self.klippy_state = klippy_state
        self.target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="offline-box"):
            yield Label("Waiting to connect", classes="panel-title")
            yield Static("", id="of-detail")
            yield Static(
                "[$text-muted]Reconnecting automatically. This closes itself "
                "as soon as the printer is ready.[/]"
            )
            with Horizontal(classes="btn-row"):
                yield Button("Firmware Restart", id="of-firmware",
                             classes="-danger")
                yield Button("Restart Klipper", id="of-restart")
                yield Button("Dismiss", id="of-dismiss")

    def on_mount(self) -> None:
        self.refresh_detail(self.connected, self.klippy_state)

    def refresh_detail(self, connected: bool, klippy_state: str) -> None:
        self.connected = connected
        self.klippy_state = klippy_state
        if not connected:
            body = (
                f"No connection to Moonraker at [b]{self.target}[/b]. "
                f"Check that the printer is powered on and on the network."
            )
            colour = "$error"
        else:
            body = STATE_HELP.get(
                klippy_state,
                f"Moonraker is connected; Klipper reports [b]{klippy_state}[/b].",
            )
            colour = "$warning"
        try:
            self.query_one("#of-detail", Static).update(
                f"[{colour}]●[/] {body}"
            )
        except Exception:
            pass

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "of-dismiss":
            self.dismiss(None)
        else:
            self.dismiss(event.button.id)
