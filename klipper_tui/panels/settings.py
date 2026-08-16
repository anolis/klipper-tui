"""Settings: choose which panels appear on the dashboard, and the theme."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from ..settings import DASHBOARD_PANELS, Settings, config_path

# key -> (toolhead field, label, unit, SET_VELOCITY_LIMIT parameter)
LIMITS = {
    "velocity": ("max_velocity", "Velocity", "mm/s", "VELOCITY"),
    "scv": ("square_corner_velocity", "Square corner velocity", "mm/s",
            "SQUARE_CORNER_VELOCITY"),
    "accel": ("max_accel", "Acceleration", "mm/s²", "ACCEL"),
    "cruise": ("minimum_cruise_ratio", "Min. cruise ratio", "%",
               "MINIMUM_CRUISE_RATIO"),
}
LIMIT_FIELDS = [(k, v[1], v[2]) for k, v in LIMITS.items()]
from ..theming import all_theme_names


class SettingsPanel(Vertical):
    def __init__(self, settings: Settings, webcam_url: str = "",
                 default_webcam_url: str = "") -> None:
        super().__init__(id="settings-panel", classes="panel")
        self.settings = settings
        self.webcam_url = webcam_url
        self.default_webcam_url = default_webcam_url
        # Limit fields the user has touched. Live values must not overwrite an
        # edit in progress — focus alone is not enough, because clicking Apply
        # moves focus away before the value is read.
        self.limits_edited: set[str] = set()

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

        yield Label("Material presets", classes="panel-title")
        yield Static(
            "[$text-muted]The buttons on the Temperature panel. Edit a row and "
            "press Apply; add or remove one and the buttons follow.[/]"
        )
        yield VerticalScroll(id="st-preset-list")
        with Horizontal(classes="btn-row"):
            yield Input(placeholder="name", id="st-preset-new-name")
            yield Input(placeholder="hotend °C", id="st-preset-new-hot",
                        type="integer")
            yield Input(placeholder="bed °C", id="st-preset-new-bed",
                        type="integer")
            yield Button("Add", id="st-preset-add", classes="-success")
            yield Button("Apply", id="st-preset-apply", classes="-primary")
        yield Static("", id="st-preset-note", classes="dim")

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
        yield Label("Machine", classes="panel-title")
        yield Static(
            "[$text-muted]Motion limits, applied live. They last until the "
            "printer restarts; Reset returns them to printer.cfg.[/]"
        )
        for key, label, unit in LIMIT_FIELDS:
            with Horizontal(classes="btn-row"):
                yield Static(f"{label}", classes="limit-label")
                yield Input(id=f"st-lim-{key}", classes="limit-input")
                yield Static(f"[$text-muted]{unit}[/]", classes="limit-unit")
        with Horizontal(classes="btn-row"):
            yield Button("Apply limits", id="st-limits-apply",
                         classes="-primary")
            yield Button("Reset", id="st-limits-reset")
        yield Static("", id="st-limits-note", classes="dim")

        yield Static(
            "[$text-muted]Firmware Restart reloads the MCU and is what you "
            "want after a shutdown or a config change. Restart Klipper "
            "reloads the host process only.[/]"
        )
        with Horizontal(classes="btn-row"):
            yield Button("Firmware Restart", id="st-firmware-restart",
                         classes="-danger")
            yield Button("Restart Klipper", id="st-klipper-restart")

        yield Static("", id="st-config-path", classes="dim")

    def on_mount(self) -> None:
        self.refresh_toggles()
        self.refresh_themes(self.app.theme)
        self.refresh_presets()
        self.query_one("#st-webcam-hint", Static).update(
            f"[$text-muted]Reset returns to {self.default_webcam_url}[/]"
        )
        self.query_one("#st-config-path", Static).update(
            f"[$text-muted]saved to {config_path()}[/]"
        )

    # -- material presets ------------------------------------------------------

    def refresh_presets(self) -> None:
        """Rebuild one editable row per preset.

        Rows are addressed by position rather than by name, since a preset can
        be called anything and widget ids cannot.
        """
        try:
            container = self.query_one("#st-preset-list", VerticalScroll)
        except Exception:
            return
        self.preset_order = list(self.settings.presets)
        container.remove_children()
        rows = []
        for index, name in enumerate(self.preset_order):
            hot, bed = self.settings.presets[name]
            rows.append(Horizontal(
                Input(value=name, id=f"st-pn-{index}", classes="preset-name"),
                Input(value=str(hot), id=f"st-ph-{index}", type="integer",
                      classes="preset-temp"),
                Input(value=str(bed), id=f"st-pb-{index}", type="integer",
                      classes="preset-temp"),
                Button("Remove", id=f"st-prm-{index}", classes="-danger"),
                classes="btn-row",
            ))
        if rows:
            container.mount(*rows)
        self._note("")

    def _note(self, message: str) -> None:
        try:
            self.query_one("#st-preset-note", Static).update(message)
        except Exception:
            pass

    def read_presets(self) -> dict | None:
        """Collect the edited rows. None if anything is unusable."""
        collected: dict[str, tuple[int, int]] = {}
        for index in range(len(getattr(self, "preset_order", []))):
            try:
                name = self.query_one(f"#st-pn-{index}", Input).value.strip()
                hot = self.query_one(f"#st-ph-{index}", Input).value.strip()
                bed = self.query_one(f"#st-pb-{index}", Input).value.strip()
            except Exception:
                continue
            if not name:
                self._note("[$error]A preset needs a name.[/]")
                return None
            try:
                pair = (int(hot), int(bed))
            except ValueError:
                self._note(f"[$error]{name}: both temperatures must be "
                           f"numbers.[/]")
                return None
            if name in collected:
                self._note(f"[$error]Two presets are both called {name}.[/]")
                return None
            collected[name] = pair
        return collected

    def new_preset(self) -> tuple[str, tuple[int, int]] | None:
        name = self.query_one("#st-preset-new-name", Input).value.strip()
        hot = self.query_one("#st-preset-new-hot", Input).value.strip()
        bed = self.query_one("#st-preset-new-bed", Input).value.strip()
        if not name:
            self._note("[$error]Give the new preset a name.[/]")
            return None
        if name in self.settings.presets:
            self._note(f"[$error]{name} already exists.[/]")
            return None
        try:
            pair = (int(hot), int(bed or 0))
        except ValueError:
            self._note("[$error]Temperatures must be numbers.[/]")
            return None
        return name, pair

    def clear_new_preset(self) -> None:
        for widget_id in ("#st-preset-new-name", "#st-preset-new-hot",
                          "#st-preset-new-bed"):
            try:
                self.query_one(widget_id, Input).value = ""
            except Exception:
                pass

    def preset_at(self, index: int) -> str | None:
        order = getattr(self, "preset_order", [])
        return order[index] if 0 <= index < len(order) else None

    # -- motion limits ---------------------------------------------------------

    def on_input_changed(self, event) -> None:
        widget_id = event.input.id or ""
        if widget_id.startswith("st-lim-"):
            self.limits_edited.add(widget_id.removeprefix("st-lim-"))

    def update_status(self, status: dict) -> None:
        """Show the live limits, leaving anything edited alone."""
        toolhead = status.get("toolhead") or {}
        settings = ((status.get("configfile") or {}).get("settings") or {})
        self.limit_defaults = settings.get("printer") or {}
        for key, (field, _, _, _) in LIMITS.items():
            value = toolhead.get(field)
            if value is None:
                continue
            try:
                widget = self.query_one(f"#st-lim-{key}", Input)
            except Exception:
                continue
            if key in self.limits_edited:
                continue  # an edit is pending; do not clobber it
            formatted = self._format_limit(key, value)
            if widget.value != formatted:
                widget.value = formatted
                # Setting the value fires Input.Changed, which would otherwise
                # mark the field as edited by the user.
                self.limits_edited.discard(key)

    @staticmethod
    def _format_limit(key: str, value: float) -> str:
        # Klipper carries the cruise ratio as 0-1; it reads better as a
        # percentage, which is also how Mainsail shows it.
        if key == "cruise":
            return f"{value * 100:g}"
        return f"{value:g}"

    def clear_limit_edits(self) -> None:
        self.limits_edited.clear()

    def read_limits(self) -> dict | None:
        """Collect the edited limits as SET_VELOCITY_LIMIT parameters."""
        params: dict[str, float] = {}
        for key, (_, label, _, parameter) in LIMITS.items():
            try:
                raw = self.query_one(f"#st-lim-{key}", Input).value.strip()
            except Exception:
                continue
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                self._limits_note(f"[$error]{label} must be a number.[/]")
                return None
            if key == "cruise":
                if not 0 <= value < 100:
                    self._limits_note(
                        "[$error]Min. cruise ratio must be 0 or more and "
                        "under 100%.[/]")
                    return None
                value /= 100.0
            elif value <= 0:
                self._limits_note(f"[$error]{label} must be above zero.[/]")
                return None
            params[parameter] = value
        return params

    def default_limits(self) -> dict:
        params = {}
        for key, (field, _, _, parameter) in LIMITS.items():
            value = getattr(self, "limit_defaults", {}).get(field)
            if value is not None:
                params[parameter] = float(value)
        return params

    def _limits_note(self, message: str) -> None:
        try:
            self.query_one("#st-limits-note", Static).update(message)
        except Exception:
            pass

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
