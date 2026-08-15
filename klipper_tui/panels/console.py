"""Gcode console: response log plus command input with history."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog


class ConsolePanel(Vertical):
    """Console output.

    RichLog renders *Rich* markup, not Textual's content markup, so ``$token``
    styles are not understood here and would raise a MarkupError. Colours are
    resolved from the active theme to concrete hex at write time instead.
    """

    def __init__(self) -> None:
        super().__init__(id="console-panel")
        self._history: list[str] = []
        self._hist_pos = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="console-log", markup=True, wrap=True, highlight=False)
        yield Input(placeholder="Send gcode…  (↑/↓ history)", id="console-input")

    # -- colours ---------------------------------------------------------------

    def _color(self, attribute: str, fallback: str) -> str:
        """A concrete colour from the active theme, safe for Rich markup."""
        try:
            value = getattr(self.app.current_theme, attribute, None)
        except Exception:
            value = None
        # Some theme tokens resolve to expressions like "auto 60%", which Rich
        # cannot parse; only accept plain colours.
        if isinstance(value, str) and value.startswith("#"):
            return value
        return fallback

    # -- writing ---------------------------------------------------------------

    def write_response(self, text: str) -> None:
        log = self.query_one("#console-log", RichLog)
        error = self._color("error", "#d41216")
        for line in text.splitlines():
            if not line:
                continue
            escaped = self._esc(line)
            if line.startswith("!!"):
                log.write(f"[{error} bold]{escaped}[/]")
            elif line.startswith("//"):
                log.write(f"[dim]{escaped}[/]")
            else:
                log.write(escaped)

    def write_echo(self, text: str) -> None:
        accent = self._color("accent", "#2196f3")
        self.query_one("#console-log", RichLog).write(
            f"[{accent} bold]> {self._esc(text)}[/]"
        )

    def write_system(self, text: str) -> None:
        warning = self._color("warning", "#ff9800")
        self.query_one("#console-log", RichLog).write(
            f"[{warning}]{self._esc(text)}[/]"
        )

    # -- history ---------------------------------------------------------------

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
        # Rich markup is enabled, so literal brackets must be escaped.
        return text.replace("[", "\\[")
