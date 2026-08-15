"""Gcode console: response log plus command input with history."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog


class ConsolePanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="console-panel")
        self._history: list[str] = []
        self._hist_pos = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="console-log", markup=True, wrap=True, highlight=False)
        yield Input(placeholder="Send gcode…  (↑/↓ history)", id="console-input")

    def write_response(self, text: str) -> None:
        log = self.query_one("#console-log", RichLog)
        for line in text.splitlines():
            if not line:
                continue
            if line.startswith("!!"):
                log.write(f"[#D41216 b]{self._esc(line)}[/]")
            elif line.startswith("//"):
                log.write(f"[#9e9e9e]{self._esc(line)}[/]")
            else:
                log.write(f"[#e0e0e0]{self._esc(line)}[/]")

    def write_echo(self, text: str) -> None:
        self.query_one("#console-log", RichLog).write(
            f"[#2196f3 b]> {self._esc(text)}[/]"
        )

    def write_system(self, text: str) -> None:
        self.query_one("#console-log", RichLog).write(
            f"[#ff9800]{self._esc(text)}[/]"
        )

    def push_history(self, cmd: str) -> None:
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
        self._hist_pos = len(self._history)

    def recall(self, delta: int) -> str | None:
        if not self._history:
            return None
        self._hist_pos = max(0, min(len(self._history), self._hist_pos + delta))
        if self._hist_pos >= len(self._history):
            return ""
        return self._history[self._hist_pos]

    @staticmethod
    def _esc(text: str) -> str:
        # RichLog has markup enabled, so literal brackets must be escaped.
        return text.replace("[", "\\[")
