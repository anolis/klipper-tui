"""Gcode console: response log plus command input with history."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog


# printer.gcode.help lists the extended commands, but not the plain G/M codes:
# Klipper registers those without help text. They are the ones people type most,
# so completion would be missing the obvious without this.
COMMON_GCODE = [
    "G0", "G1", "G4", "G28", "G90", "G91", "G92",
    "M18", "M82", "M83", "M84", "M104", "M105", "M106", "M107", "M109",
    "M112", "M114", "M115", "M117", "M140", "M190", "M204", "M220", "M221",
]


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
        self.commands: list[str] = []

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

    # -- completion --------------------------------------------------------------

    def set_commands(self, commands: list[str]) -> None:
        self.commands = sorted(set(commands))

    def complete(self, text: str) -> tuple[str, list[str]]:
        """Complete a partly typed command.

        Returns what the field should now contain and any remaining
        candidates. Only the first word is completed: everything after it is
        arguments, which differ per command.
        """
        if not text or " " in text.strip():
            return text, []
        prefix = text.strip().upper()
        matches = [c for c in self.commands if c.upper().startswith(prefix)]
        if not matches:
            return text, []
        if len(matches) == 1:
            return matches[0] + " ", []
        # Fill in as far as every candidate agrees, then show the choices.
        # The shared part is never shorter than what was typed, so this also
        # fixes up the case of a lowercase command.
        shared = matches[0]
        for candidate in matches[1:]:
            while not candidate.upper().startswith(shared.upper()):
                shared = shared[:-1]
        return (shared if len(shared) >= len(prefix) else text), matches

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
