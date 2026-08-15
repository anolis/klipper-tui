"""Settings: choose which panels appear on the dashboard, and the theme."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

from ..settings import DASHBOARD_PANELS, Settings, config_path


class SettingsPanel(Vertical):
    def __init__(self, settings: Settings) -> None:
        super().__init__(id="settings-panel", classes="panel")
        self.settings = settings

    def compose(self) -> ComposeResult:
        yield Label("Dashboard panels", classes="panel-title")
        yield Static(
            "[$text-muted]Any panel can be shown on the dashboard as well as "
            "on its own tab. Choices are saved automatically.[/]"
        )
        for key, (label, _) in DASHBOARD_PANELS.items():
            with Horizontal(classes="btn-row setting-row"):
                yield Button("", id=f"st-toggle-{key}")
                yield Static(label, classes="setting-label")

        yield Label("Theme", classes="panel-title")
        yield Static(
            "[$text-muted]Press [/][b]t[/b][$text-muted] to cycle themes, or "
            "use the command palette with [/][b]ctrl+p[/b][$text-muted].[/]"
        )
        yield Static("", id="st-config-path", classes="dim")

    def on_mount(self) -> None:
        self.refresh_toggles()
        self.query_one("#st-config-path", Static).update(
            f"[$text-muted]saved to {config_path()}[/]"
        )

    def refresh_toggles(self) -> None:
        for key in DASHBOARD_PANELS:
            try:
                button = self.query_one(f"#st-toggle-{key}", Button)
            except Exception:
                continue
            on = self.settings.visible(key)
            button.label = "● shown" if on else "○ hidden"
            button.set_class(on, "-success")
            button.set_class(not on, "-muted")
