"""Files panel: browse gcode files and control the running job."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static

from ..format import filesize


class FilesPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="files-panel")
        self.files: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Label("G-code Files", classes="panel-title")

        with Horizontal(classes="btn-row"):
            yield Button("Refresh", id="fl-refresh")
            yield Button("Print Selected", id="fl-print", classes="-primary")
            yield Button("Pause", id="fl-pause")
            yield Button("Resume", id="fl-resume", classes="-success")
            yield Button("Cancel", id="fl-cancel", classes="-danger")

        yield DataTable(id="file-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="fl-info", classes="dim")

    def on_mount(self) -> None:
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add the columns once.

        A panel mounted onto the dashboard is handed the cached file list to
        catch up, which can arrive before on_mount has run — adding rows to a
        table with no columns raises.
        """
        table = self.query_one("#file-table", DataTable)
        if table.columns:
            return
        table.add_column("Filename", width=64)
        table.add_column("Size", width=10)
        table.add_column("Modified", width=16)

    def load_files(self, files: list[dict]) -> None:
        # Newest first, matching Mainsail's default sort.
        self.files = sorted(
            files, key=lambda f: f.get("modified", 0), reverse=True
        )
        self._ensure_columns()
        table = self.query_one("#file-table", DataTable)
        table.clear()
        for f in self.files:
            table.add_row(
                f.get("path", "?"),
                filesize(f.get("size")),
                self._when(f.get("modified")),
            )
        self.query_one("#fl-info", Static).update(
            f"{len(self.files)} file(s)"
        )

    def selected_file(self) -> str | None:
        table = self.query_one("#file-table", DataTable)
        if not self.files or table.cursor_row is None:
            return None
        if table.cursor_row >= len(self.files):
            return None
        return self.files[table.cursor_row].get("path")

    @staticmethod
    def _when(ts: float | None) -> str:
        if not ts:
            return "-"
        from datetime import datetime

        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
