"""A yes/no modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Returns True if confirmed, False if dismissed."""

    BINDINGS = [("escape", "dismiss_false", "Cancel")]

    def __init__(self, title: str, message: str,
                 confirm_label: str = "Continue",
                 confirm_variant: str = "-primary") -> None:
        super().__init__()
        self.title_text = title
        self.message = message
        self.confirm_label = confirm_label
        self.confirm_variant = confirm_variant

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.title_text, classes="panel-title")
            yield Static(self.message)
            with Horizontal(classes="btn-row"):
                yield Button(self.confirm_label, id="cf-yes",
                             classes=self.confirm_variant)
                yield Button("Cancel", id="cf-no")

    def action_dismiss_false(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "cf-yes")
