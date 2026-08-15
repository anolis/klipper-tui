"""Settings: choose which panels appear on the dashboard, and the theme."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

from ..settings import DASHBOARD_PANELS, Settings, config_path
from ..theming import all_theme_names


class SettingsPanel(Vertical):
    def __init__(self, settings: Settings, webcam_url: str = "",
                 default_webcam_url: str = "") -> None:
        super().__init__(id="settings-panel", classes="panel")
        self.settings = settings
        self.webcam_url = webcam_url
        self.default_webcam_url = default_webcam_url

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

        yield Label("Webcam", classes="panel-title")
        with Horizontal(classes="btn-row"):
            yield Input(value=self.webcam_url, id="st-webcam-url",
                        placeholder="MJPEG snapshot URL")
            yield Button("Apply", id="st-webcam-apply", classes="-primary")
            yield Button("Reset", id="st-webcam-reset")
        yield Static("", id="st-webcam-hint", classes="dim")

        yield Label("Theme", classes="panel-title")
        for name in all_theme_names():
            with Horizontal(classes="btn-row setting-row"):
                yield Button("", id=f"st-theme-{name}")
                yield Static(name, classes="setting-label")
        yield Static("", id="st-config-path", classes="dim")

    def on_mount(self) -> None:
        self.refresh_toggles()
        self.refresh_themes(self.app.theme)
        self.query_one("#st-webcam-hint", Static).update(
            f"[$text-muted]Reset returns to {self.default_webcam_url}[/]"
        )
        self.query_one("#st-config-path", Static).update(
            f"[$text-muted]saved to {config_path()}[/]"
        )

    def refresh_themes(self, active: str) -> None:
        for name in all_theme_names():
            try:
                button = self.query_one(f"#st-theme-{name}", Button)
            except Exception:
                continue
            chosen = name == active
            button.label = "● active" if chosen else "○ use"
            button.set_class(chosen, "-primary")
            button.set_class(not chosen, "-muted")

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
