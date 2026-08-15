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
from .panels.status import StatusPanel
from .panels.temperature import PRESETS, TemperaturePanel
from .panels.tempgraph import RANGES, TempGraphPanel
from .panels.toolhead import STEP_SIZES, ToolheadPanel
from .panels.webcam import FPS_CHOICES, WebcamPanel


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
        ("ctrl+e", "estop", "E-STOP"),
    ]

    def __init__(
        self,
        host: str,
        port: int = 7125,
        webcam_url: str | None = None,
        renderer: str = "auto",
    ) -> None:
        super().__init__()
        self.client = MoonrakerClient(host, port)
        self.sub_title = f"{host}:{port}"
        self.webcam_url = webcam_url or f"http://{host}/webcam/?action=snapshot"
        self.renderer = renderer
        self._ws_task: asyncio.Task | None = None

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                with VerticalScroll():
                    with Container(id="dash-grid"):
                        yield StatusPanel()
                        yield TemperaturePanel()
                    yield ExtruderPanel()
            with TabPane("Graph", id="graph"):
                yield TempGraphPanel()
            with TabPane("Console", id="console"):
                yield ConsolePanel()
            with TabPane("Move", id="move"):
                with VerticalScroll():
                    yield ToolheadPanel()
            with TabPane("Files", id="files"):
                yield FilesPanel()
            with TabPane("Mesh", id="mesh"):
                with VerticalScroll():
                    yield BedMeshPanel()
            with TabPane("Webcam", id="webcam"):
                yield WebcamPanel(self.webcam_url, self.renderer)
        yield Static("", id="statusbar")
        yield Footer()

    # -- lifecycle ------------------------------------------------------------

    def on_mount(self) -> None:
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
            self.query_one(StatusPanel).update_status(
                status, self.client.klippy_state
            )
            self.query_one(TemperaturePanel).update_status(status)
            self.query_one(ExtruderPanel).update_status(status)
            self.query_one(BedMeshPanel).update_status(status)
            self.query_one(TempGraphPanel).append_live(status)
        except Exception:
            # Panels may not be mounted yet during the first status burst.
            pass

    def _handle_gcode_response(self, text: str) -> None:
        try:
            self.query_one(ConsolePanel).write_response(text)
        except Exception:
            pass

    def _handle_conn(self, connected: bool, klippy_state: str) -> None:
        try:
            bar = self.query_one("#statusbar", Static)
        except Exception:
            return
        if connected:
            color = "#4caf50" if klippy_state == "ready" else "#ff9800"
            bar.update(
                f"[{color}]●[/] connected  [#9e9e9e]klippy:[/] {klippy_state}"
            )
            if klippy_state == "ready":
                self.refresh_files()
                self.run_worker(self._seed_graph())
        else:
            bar.update("[#D41216]●[/] disconnected — retrying…")

    # -- helpers --------------------------------------------------------------

    async def send(self, script: str, echo: bool = True) -> None:
        console = self.query_one(ConsolePanel)
        if echo:
            console.write_echo(script.replace("\n", " ; "))
        try:
            await self.client.gcode(script)
        except MoonrakerError as exc:
            console.write_system(f"error: {exc}")
            self.notify(str(exc), severity="error", title="Command failed")

    def _float(self, widget_id: str, default: float) -> float:
        try:
            return float(self.query_one(widget_id, Input).value)
        except (ValueError, TypeError):
            return default

    # -- actions --------------------------------------------------------------

    def action_show_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

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
            self.query_one(TempGraphPanel).seed(store)
        except Exception:
            pass

    async def _load_files(self) -> None:
        try:
            files = await self.client.list_gcode_files()
            self.query_one(FilesPanel).load_files(files)
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
            self.query_one(ToolheadPanel).step = float(raw)
        elif bid in ("th-x-neg", "th-x-pos", "th-y-neg", "th-y-pos",
                     "th-z-neg", "th-z-pos"):
            panel = self.query_one(ToolheadPanel)
            axis = bid.split("-")[1].upper()
            direction = 1 if bid.endswith("pos") else -1
            await self.send(panel.jog_gcode(axis, direction))
        elif bid == "th-motors-off":
            await self.send("M84")
        elif bid == "th-ztilt":
            await self.send("Z_TILT_ADJUST")

        # Extruder
        elif bid in ("ex-extrude", "ex-retract"):
            panel = self.query_one(ExtruderPanel)
            if not panel.can_extrude(self.client.status):
                self.notify(
                    "Hotend below min_extrude_temp (170°C)",
                    severity="warning",
                    title="Too cold",
                )
                return
            amount = self._float("#ex-amount", 25)
            feed = self._float("#ex-feedrate", 5)
            direction = 1 if bid == "ex-extrude" else -1
            await self.send(panel.move_gcode(amount, feed, direction))
        elif bid == "ex-load":
            await self._filament_macro("LOAD_FILAMENT")
        elif bid == "ex-unload":
            await self._filament_macro("UNLOAD_FILAMENT")
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

        # Temperature graph
        elif bid.startswith("tg-range-"):
            self.query_one(TempGraphPanel).set_range(
                int(bid.removeprefix("tg-range-"))
            )
        elif bid == "tg-targets":
            on = self.query_one(TempGraphPanel).toggle_targets()
            event.button.label = "Targets" if on else "No targets"

        # Webcam
        elif bid == "wc-toggle":
            running = self.query_one(WebcamPanel).toggle()
            event.button.label = "Pause" if running else "Resume"
        elif bid.startswith("wc-fps-"):
            self.query_one(WebcamPanel).set_fps(int(bid.removeprefix("wc-fps-")))

        # Bed mesh
        elif bid == "bm-calibrate":
            await self.send("BED_MESH_CALIBRATE")
        elif bid == "bm-load":
            await self.send("BED_MESH_PROFILE LOAD=default")
        elif bid == "bm-save":
            await self.send("SAVE_CONFIG")
        elif bid == "bm-clear":
            await self.send("BED_MESH_CLEAR")

    async def _filament_macro(self, macro: str) -> None:
        """Use the printer's own macro if defined, else a safe generic move."""
        panel = self.query_one(ExtruderPanel)
        if not panel.can_extrude(self.client.status):
            self.notify(
                "Hotend below min_extrude_temp (170°C)",
                severity="warning",
                title="Too cold",
            )
            return
        macros = {
            k.removeprefix("gcode_macro ").upper()
            for k in self.client.status
            if k.startswith("gcode_macro ")
        }
        if macro in macros:
            await self.send(macro)
            return
        # No macro configured — fall back to a plain relative extrude move.
        feed = self._float("#ex-feedrate", 5)
        length = 50 if macro == "LOAD_FILAMENT" else -50
        self.query_one(ConsolePanel).write_system(
            f"{macro} macro not defined; using generic {length:+g}mm move"
        )
        await self.send(f"M83\nG1 E{length:g} F{feed * 60:g}\nM82")

    async def _start_print(self) -> None:
        filename = self.query_one(FilesPanel).selected_file()
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
