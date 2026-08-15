"""Main Textual application."""

from __future__ import annotations

import asyncio

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Static,
    TabbedContent,
    TabPane,
)

from .moonraker import MoonrakerClient, MoonrakerError
from .panels.bedmesh import BedMeshPanel
from .panels.console import ConsolePanel
from .panels.extruder import ExtruderPanel
from .panels.files import FilesPanel
from .panels.position import PositionPanel
from .panels.preheat import PreheatScreen
from .panels.status import StatusPanel
from .panels.tuning import FACTORS, TuningPanel
from .panels.temperature import PRESETS, TemperaturePanel, set_presets
from .panels.tempgraph import RANGES, TempGraphPanel
from .panels.toolhead import STEP_SIZES, ToolheadPanel
from .panels.settings import SettingsPanel
from .panels.webcam import FPS_CHOICES, WebcamPanel
from .settings import DASHBOARD_PANELS, Settings
from .theming import DEFAULT_THEME, all_theme_names, register as register_themes


class KlipperTUI(App):
    CSS_PATH = "app.tcss"
    TITLE = "Klipper TUI"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "show_tab('dashboard')", "Dashboard"),
        ("c", "show_tab('console')", "Console"),
        ("m", "show_tab('move')", "Move"),
        ("f", "show_tab('files')", "Files"),
        ("b", "show_tab('mesh')", "Mesh"),
        ("w", "show_tab('webcam')", "Webcam"),
        ("g", "show_tab('graph')", "Graph"),
        ("t", "next_theme", "Theme"),
        ("s", "show_tab('settings')", "Settings"),
        ("ctrl+e", "estop", "E-STOP"),
    ]

    def __init__(
        self,
        host: str,
        port: int = 7125,
        webcam_url: str | None = None,
        renderer: str = "auto",
        theme: str = DEFAULT_THEME,
    ) -> None:
        super().__init__()
        self.client = MoonrakerClient(host, port)
        self.sub_title = f"{host}:{port}"
        self.default_webcam_url = f"http://{host}/webcam/?action=snapshot"
        self.renderer = renderer
        self.settings = Settings()
        set_presets(self.settings.presets)
        # An explicit flag wins over the saved override, which wins over the
        # URL derived from the host.
        self.webcam_url = (
            webcam_url or self.settings.webcam_url or self.default_webcam_url
        )
        self._theme_name = self.settings.theme or theme
        self._last_temp_store: dict | None = None
        self._last_files: list | None = None
        self._ws_task: asyncio.Task | None = None

        # Register before the stylesheet is parsed so theme variables resolve.
        register_themes(self)
        if self._theme_name in all_theme_names():
            self.theme = self._theme_name

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                yield VerticalScroll(id="dash-panels")
            with TabPane("Graph", id="graph"):
                yield TempGraphPanel()
            with TabPane("Console", id="console"):
                yield ConsolePanel()
            with TabPane("Move", id="move"):
                with VerticalScroll():
                    yield ToolheadPanel()
                    yield PositionPanel()
            with TabPane("Files", id="files"):
                yield FilesPanel()
            with TabPane("Mesh", id="mesh"):
                with VerticalScroll():
                    yield BedMeshPanel()
            with TabPane("Webcam", id="webcam"):
                yield WebcamPanel(self.webcam_url, self.renderer)
            with TabPane("Settings", id="settings"):
                with VerticalScroll():
                    yield SettingsPanel(
                        self.settings, self.webcam_url,
                        self.default_webcam_url,
                    )
        yield Static("", id="statusbar")
        yield Footer()

    # -- dashboard composition ------------------------------------------------

    def _make_panel(self, key: str):
        """A fresh instance of a panel, for mounting on the dashboard."""
        if key == "status":
            return StatusPanel()
        if key == "temperature":
            return TemperaturePanel()
        if key == "tempgraph":
            return TempGraphPanel(compact=True)
        if key == "tuning":
            return TuningPanel()
        if key == "extruder":
            return ExtruderPanel(self.settings.filament_length)
        if key == "toolhead":
            return ToolheadPanel()
        if key == "bedmesh":
            return BedMeshPanel()
        if key == "position":
            return PositionPanel()
        if key == "webcam":
            return WebcamPanel(self.webcam_url, self.renderer)
        if key == "console":
            return ConsolePanel()
        if key == "files":
            return FilesPanel()
        return None

    async def rebuild_dashboard(self) -> None:
        """Remount the dashboard from the saved panel selection.

        Panels are created and destroyed rather than merely hidden, so a panel
        switched off stops doing work (the webcam stops polling, for one).
        Removal is awaited: mounting a replacement before the old widget is
        gone collides on the panel's id.
        """
        container = self.query_one("#dash-panels", VerticalScroll)
        # Removal must be awaited or the replacements collide on widget ids.
        await container.remove_children()

        panels = []
        for key in DASHBOARD_PANELS:
            if self.settings.visible(key):
                panel = self._make_panel(key)
                if panel is not None:
                    panel.add_class("on-dashboard")
                    panels.append(panel)
        if panels:
            # Not awaited: during start-up the app is still inside its own
            # mount pipeline, and waiting on a child mount never returns.
            container.mount(*panels)
        self.call_after_refresh(self._prime_new_panels)

    def _prime_new_panels(self) -> None:
        """Give freshly mounted panels the state they missed."""
        if self.client.status:
            self._handle_status(self.client.status)
        if self._last_temp_store:
            for graph in self.query(TempGraphPanel):
                graph.seed(self._last_temp_store)
        if self._last_files is not None:
            for files in self.query(FilesPanel):
                files.load_files(self._last_files)

    # -- lifecycle ------------------------------------------------------------

    def on_mount(self) -> None:
        # Build once the first paint is done, so the tab panes exist.
        self.call_after_refresh(
            lambda: self.run_worker(self.rebuild_dashboard(), exclusive=True)
        )

        self.client.on_status(self._handle_status)
        self.client.on_gcode_response(self._handle_gcode_response)
        self.client.on_connection_change(self._handle_conn)
        self._ws_task = asyncio.create_task(self.client.run())

    async def on_unmount(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()

    # -- client callbacks -----------------------------------------------------

    def _handle_status(self, status: dict) -> None:
        try:
            for panel in self.query(StatusPanel):
                panel.update_status(status, self.client.klippy_state)
            for panel_type in (TemperaturePanel, ExtruderPanel, BedMeshPanel,
                               PositionPanel, TuningPanel):
                for panel in self.query(panel_type):
                    panel.update_status(status)
            # A panel can appear on its own tab and on the dashboard at once.
            for graph in self.query(TempGraphPanel):
                graph.append_live(status)
        except Exception:
            # Panels may not be mounted yet during the first status burst.
            pass

    def _handle_gcode_response(self, text: str) -> None:
        try:
            for console in self.query(ConsolePanel):
                console.write_response(text)
        except Exception:
            pass

    def _handle_conn(self, connected: bool, klippy_state: str) -> None:
        try:
            bar = self.query_one("#statusbar", Static)
        except Exception:
            return
        if connected:
            color = "$success" if klippy_state == "ready" else "$warning"
            bar.update(
                f"[{color}]●[/] connected  [$text-muted]klippy:[/] "
                f"{klippy_state}"
            )
            if klippy_state == "ready":
                self.refresh_files()
                self.run_worker(self._seed_graph())
        else:
            bar.update("[$error]●[/] disconnected — retrying…")

    # -- helpers --------------------------------------------------------------

    def _console_write(self, method: str, text: str) -> None:
        for console in self.query(ConsolePanel):
            getattr(console, method)(text)

    async def send(self, script: str, echo: bool = True) -> None:
        if echo:
            self._console_write("write_echo", script.replace("\n", " ; "))
        try:
            await self.client.gcode(script)
        except MoonrakerError as exc:
            self._console_write("write_system", f"error: {exc}")
            self.notify(str(exc), severity="error", title="Command failed")

    def _float(self, widget_id: str, default: float,
               within=None) -> float:
        """Read a numeric input, scoped to a panel when one is given.

        Panels can exist twice (own tab plus dashboard), so an unscoped
        query would be ambiguous.
        """
        node = within if within is not None else self
        try:
            return float(node.query_one(widget_id, Input).value)
        except Exception:
            return default

    @staticmethod
    def _owner(widget, panel_type):
        """The panel instance containing this widget, or None."""
        for node in widget.ancestors:
            if isinstance(node, panel_type):
                return node
        return None

    # -- actions --------------------------------------------------------------

    def action_show_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def set_theme(self, name: str) -> None:
        if name not in all_theme_names():
            return
        self.theme = name
        self.settings.theme = name
        self.settings.save()
        for panel in self.query(SettingsPanel):
            panel.refresh_themes(name)
        self.notify(name, title="Theme")

    def action_next_theme(self) -> None:
        names = all_theme_names()
        try:
            index = names.index(self.theme)
        except ValueError:
            index = -1
        self.set_theme(names[(index + 1) % len(names)])

    async def action_estop(self) -> None:
        try:
            await self.client.emergency_stop()
            self.notify("Emergency stop sent", severity="error", title="E-STOP")
        except MoonrakerError as exc:
            self.notify(str(exc), severity="error")

    def refresh_files(self) -> None:
        self.run_worker(self._load_files(), exclusive=True)

    async def _seed_graph(self) -> None:
        try:
            store = await self.client.temperature_store()
            self._last_temp_store = store
            for graph in self.query(TempGraphPanel):
                graph.seed(store)
        except Exception:
            pass

    async def _load_files(self) -> None:
        try:
            files = await self.client.list_gcode_files()
            self._last_files = files
            for panel in self.query(FilesPanel):
                panel.load_files(files)
        except (MoonrakerError, Exception):
            pass

    # -- console input --------------------------------------------------------

    @on(Input.Submitted, "#console-input")
    async def _console_submit(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        if not cmd:
            return
        console = self.query_one(ConsolePanel)
        console.push_history(cmd)
        event.input.value = ""
        await self.send(cmd)

    @on(Input.Changed, "#bm-count")
    def _mesh_count_changed(self, event: Input.Changed) -> None:
        panel = self._owner(event.input, BedMeshPanel)
        if panel is not None:
            panel.refresh_estimate()

    @on(Input.Submitted, "#tn-speed-input")
    @on(Input.Submitted, "#tn-flow-input")
    async def _tuning_submit(self, event: Input.Submitted) -> None:
        key = "speed" if "speed" in (event.input.id or "") else "flow"
        try:
            value = float(event.value)
        except ValueError:
            return
        event.input.value = ""
        panel = self._owner(event.input, TuningPanel) or next(
            iter(self.query(TuningPanel)), None)
        if panel is None:
            return
        await self.send(panel.command_for(key, value))

    async def on_key(self, event: events.Key) -> None:
        if event.key not in ("up", "down"):
            return
        if self.focused is None or self.focused.id != "console-input":
            return
        recalled = self.query_one(ConsolePanel).recall(
            -1 if event.key == "up" else 1
        )
        if recalled is not None:
            self.query_one("#console-input", Input).value = recalled
            event.prevent_default()

    # -- button routing -------------------------------------------------------

    @on(Button.Pressed)
    async def _button(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""

        # Temperature
        if bid == "tp-set":
            ext = self.query_one("#tp-in-ext", Input).value.strip()
            bed = self.query_one("#tp-in-bed", Input).value.strip()
            if ext:
                await self.send(f"SET_HEATER_TEMPERATURE HEATER=extruder TARGET={ext}")
            if bed:
                await self.send(f"SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={bed}")
        elif bid.startswith("tp-preset-"):
            name = bid.removeprefix("tp-preset-")
            hot, bed = PRESETS[name]
            await self.send(
                f"SET_HEATER_TEMPERATURE HEATER=extruder TARGET={hot}\n"
                f"SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={bed}"
            )
        elif bid == "tp-cooldown":
            await self.send(
                "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0\n"
                "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0"
            )

        # Toolhead
        elif bid == "th-home-all":
            await self.send("G28")
        elif bid in ("th-home-x", "th-home-y", "th-home-z"):
            await self.send(f"G28 {bid[-1].upper()}")
        elif bid.startswith("th-step-"):
            raw = bid.removeprefix("th-step-").replace("_", ".")
            owner = self._owner(event.button, ToolheadPanel)
            if owner is not None:
                owner.step = float(raw)
        elif bid in ("th-x-neg", "th-x-pos", "th-y-neg", "th-y-pos",
                     "th-z-neg", "th-z-pos"):
            panel = self._owner(event.button, ToolheadPanel)
            axis = bid.split("-")[1].upper()
            direction = 1 if bid.endswith("pos") else -1
            await self.send(panel.jog_gcode(axis, direction))
        elif bid == "th-motors-off":
            await self.send("M84")
        elif bid == "th-ztilt":
            await self.send("Z_TILT_ADJUST")

        # Extruder
        elif bid in ("ex-extrude", "ex-retract"):
            panel = self._owner(event.button, ExtruderPanel)
            if not panel.can_extrude(self.client.status):
                self.notify(
                    "Hotend below min_extrude_temp (170°C)",
                    severity="warning",
                    title="Too cold",
                )
                return
            amount = self._float("#ex-amount", 25, panel)
            feed = self._float("#ex-feedrate", 5, panel)
            direction = 1 if bid == "ex-extrude" else -1
            await self.send(panel.move_gcode(amount, feed, direction))
        elif bid in ("ex-load", "ex-unload"):
            # Runs in a worker so the preheat dialog can be awaited.
            owner = self._owner(event.button, ExtruderPanel)
            if owner is not None:
                self.run_worker(
                    self._filament(bid == "ex-load", owner), exclusive=True)
        elif bid == "ex-rt-apply":
            length = self.query_one("#ex-rt-len", Input).value.strip()
            speed = self.query_one("#ex-rt-speed", Input).value.strip()
            parts = []
            if length:
                parts.append(f"RETRACT_LENGTH={length}")
            if speed:
                parts.append(f"RETRACT_SPEED={speed}")
            if parts:
                await self.send("SET_RETRACTION " + " ".join(parts))

        # Files / job control
        elif bid == "fl-refresh":
            self.refresh_files()
        elif bid == "fl-print":
            await self._start_print()
        elif bid == "fl-pause":
            await self._job("print_pause", "Paused")
        elif bid == "fl-resume":
            await self._job("print_resume", "Resumed")
        elif bid == "fl-cancel":
            await self._job("print_cancel", "Cancelled")

        # Temperature graph (controls exist only on the full Graph tab)
        elif bid.startswith("tg-range-"):
            self.query_one("#tempgraph-panel", TempGraphPanel).set_range(
                int(bid.removeprefix("tg-range-"))
            )
        elif bid == "tg-targets":
            on = self.query_one("#tempgraph-panel", TempGraphPanel).toggle_targets()
            event.button.label = "Targets" if on else "No targets"

        # Settings
        elif bid in ("st-webcam-apply", "st-webcam-reset"):
            panel = self._owner(event.button, SettingsPanel)
            field = panel.query_one("#st-webcam-url", Input)
            if bid == "st-webcam-reset":
                url = self.default_webcam_url
                self.settings.webcam_url = None
            else:
                url = field.value.strip() or self.default_webcam_url
                self.settings.webcam_url = (
                    url if url != self.default_webcam_url else None
                )
            field.value = url
            self.webcam_url = url
            self.settings.save()
            for cam in self.query(WebcamPanel):
                cam.set_url(url)
            self.notify(url, title="Webcam URL")

        elif bid.startswith("st-theme-"):
            self.set_theme(bid.removeprefix("st-theme-"))

        elif bid.startswith("st-toggle-"):
            key = bid.removeprefix("st-toggle-")
            on = self.settings.toggle(key)
            for panel in self.query(SettingsPanel):
                panel.refresh_toggles()
            self.run_worker(self.rebuild_dashboard(), exclusive=True)
            label = DASHBOARD_PANELS.get(key, (key, False))[0]
            self.notify(
                f"{label} {'added to' if on else 'removed from'} dashboard",
                title="Dashboard",
            )

        # Speed / flow multipliers
        elif bid.startswith("tn-"):
            panel = self._owner(event.button, TuningPanel)
            _, key, rest = bid.split("-", 2)
            if key not in FACTORS:
                return
            if rest == "up":
                value = panel.nudge(key, 5)
            elif rest == "down":
                value = panel.nudge(key, -5)
            elif rest.startswith("set-"):
                value = float(rest.removeprefix("set-"))
            else:
                return
            await self.send(panel.command_for(key, value))

        # 3D position
        elif bid in ("ps-left", "ps-right", "ps-up", "ps-down"):
            panel = self._owner(event.button, PositionPanel)
            deltas = {
                "ps-left": (-0.25, 0.0), "ps-right": (0.25, 0.0),
                "ps-up": (0.0, 0.15), "ps-down": (0.0, -0.15),
            }
            panel.rotate(*deltas[bid])
        elif bid == "ps-zoom-in":
            self._owner(event.button, PositionPanel).zoom_by(1.25)
        elif bid == "ps-zoom-out":
            self._owner(event.button, PositionPanel).zoom_by(0.8)
        elif bid == "ps-reset":
            self._owner(event.button, PositionPanel).reset_view()
        elif bid == "ps-spin":
            spinning = self._owner(event.button, PositionPanel).toggle_spin()
            event.button.label = "Spin" if spinning else "Paused"

        # Webcam
        elif bid == "wc-toggle":
            running = self._owner(event.button, WebcamPanel).toggle()
            event.button.label = "Pause" if running else "Resume"
        elif bid.startswith("wc-fps-"):
            self._owner(event.button, WebcamPanel).set_fps(
                int(bid.removeprefix("wc-fps-")))

        # Bed mesh
        elif bid == "bm-calibrate":
            panel = self._owner(event.button, BedMeshPanel)
            count = panel.parse_count()
            if count is not None:
                problem = panel.validate_count(count)
                if problem:
                    self.notify(problem, severity="error", title="Probe count")
                    return
            await self.send(panel.calibrate_gcode())
        elif bid == "bm-load":
            await self.send("BED_MESH_PROFILE LOAD=default")
        elif bid == "bm-save":
            await self.send("SAVE_CONFIG")
        elif bid == "bm-clear":
            await self.send("BED_MESH_CLEAR")

    async def _filament(self, load: bool, panel: ExtruderPanel) -> None:
        """Load or unload, preheating first if the nozzle is too cold."""
        action = "Loading" if load else "Unloading"

        preheat = ""
        if not panel.can_extrude(self.client.status):
            current = self.client.status.get("extruder", {}).get("temperature")
            temp = await self.push_screen_wait(
                PreheatScreen(action, current)
            )
            if temp is None:
                self._console_write(
                    "write_system", f"{action.lower()} cancelled")
                return
            # M109 blocks until the nozzle reaches temperature.
            preheat = f"M104 S{temp:.0f}\nM109 S{temp:.0f}\n"
            self.notify(f"Heating to {temp:.0f}°C…", title=action)

        length = self._float("#ex-fil-len", 1000, panel)
        speed = self._float("#ex-fil-speed", 50, panel)
        script = (
            panel.load_gcode(length, speed) if load
            else panel.unload_gcode(length, speed)
        )

        self._console_write(
            "write_system",
            f"{action} {length:g}mm at {speed:g}mm/s"
            + (" after preheat" if preheat else ""),
        )
        try:
            # Heating plus a metre of filament takes minutes, not seconds.
            await self.client.gcode(preheat + script, timeout=900)
            self.notify(f"{action} complete", title="Filament")
        except MoonrakerError as exc:
            self._console_write("write_system", f"error: {exc}")
            self.notify(str(exc), severity="error", title=action)

    def _files_selection(self) -> str | None:
        for panel in self.query(FilesPanel):
            chosen = panel.selected_file()
            if chosen:
                return chosen
        return None

    async def _start_print(self) -> None:
        filename = self._files_selection()
        if not filename:
            self.notify("No file selected", severity="warning")
            return
        try:
            await self.client.print_start(filename)
            self.notify(f"Started {filename}", title="Print")
        except MoonrakerError as exc:
            self.notify(str(exc), severity="error", title="Print failed")

    async def _job(self, method: str, label: str) -> None:
        try:
            await getattr(self.client, method)()
            self.notify(label, title="Job")
        except MoonrakerError as exc:
            self.notify(str(exc), severity="error")
