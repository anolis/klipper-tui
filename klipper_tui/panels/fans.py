"""Fan control.

Fans are discovered from the printer objects rather than assumed, because
which ones exist and how each is driven depends entirely on the config:

  fan                the part cooling fan, driven by M106/M107
  fan_generic NAME   driven by SET_FAN_SPEED
  heater_fan NAME    Klipper runs it with the heater; read-only here
  controller_fan     Klipper runs it with the steppers; read-only
  temperature_fan    Klipper runs it to a target; read-only
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

PRESETS = [0, 25, 50, 75, 100]
BAR_WIDTH = 28

# Object prefix -> whether we can drive it.
AUTOMATIC = ("heater_fan ", "controller_fan ", "temperature_fan ")


def is_fan(object_name: str) -> bool:
    return (object_name == "fan"
            or object_name.startswith("fan_generic ")
            or object_name.startswith(AUTOMATIC))


LABEL_WIDTH = 16


def fan_label(object_name: str) -> str:
    if object_name == "fan":
        name = "Part cooling"
    else:
        raw = object_name.split(" ", 1)[-1].replace("_", " ")
        name = raw[:1].upper() + raw[1:]
    # A long name would otherwise run into the bar beside it.
    if len(name) > LABEL_WIDTH - 1:
        name = name[: LABEL_WIDTH - 2] + "…"
    return name


def controllable(object_name: str) -> bool:
    return not object_name.startswith(AUTOMATIC)


def speed_command(object_name: str, percent: float) -> str:
    """How to set this particular fan."""
    if object_name == "fan":
        # The part fan predates SET_FAN_SPEED and takes 0-255.
        if percent <= 0:
            return "M107"
        return f"M106 S{round(percent * 255 / 100)}"
    name = object_name.split(" ", 1)[-1]
    return f"SET_FAN_SPEED FAN={name} SPEED={percent / 100:.2f}"


class FansPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="fans-panel", classes="panel")
        self.fans: list[str] = []
        self.speeds: dict[str, float] = {}

    def compose(self) -> ComposeResult:
        yield Label("Fans", classes="panel-title")
        yield Static("", id="fn-empty", classes="dim")
        yield Vertical(id="fn-list")
        yield Static("", id="fn-note", classes="dim")

    def update_status(self, status: dict) -> None:
        found = sorted(name for name in status if is_fan(name))
        if found != self.fans:
            self.fans = found
            self._rebuild()

        for name in self.fans:
            speed = (status.get(name) or {}).get("speed")
            if speed is not None:
                self.speeds[name] = float(speed) * 100
        self._refresh()

    def _rebuild(self) -> None:
        try:
            container = self.query_one("#fn-list", Vertical)
            empty = self.query_one("#fn-empty", Static)
        except Exception:
            return
        container.remove_children()
        if not self.fans:
            empty.update("[$text-muted]No fans reported by the printer.[/]")
            return
        empty.update("")

        rows = []
        for index, name in enumerate(self.fans):
            rows.append(Static("", id=f"fn-bar-{index}"))
            if not controllable(name):
                continue
            buttons = [Button("−10", id=f"fn-down-{index}"),
                       Button("+10", id=f"fn-up-{index}")]
            buttons += [Button(f"{p}%", id=f"fn-set-{index}-{p}")
                        for p in PRESETS]
            buttons += [
                Input(placeholder="%", id=f"fn-in-{index}",
                      classes="fan-input", type="number"),
                Button("Set", id=f"fn-apply-{index}", classes="-primary"),
            ]
            rows.append(Horizontal(*buttons, classes="btn-row compact-row"))
        if rows:
            container.mount(*rows)

    def _refresh(self) -> None:
        for index, name in enumerate(self.fans):
            percent = self.speeds.get(name, 0.0)
            filled = int(round(percent / 100 * BAR_WIDTH))
            colour = "$text-muted" if percent <= 0 else "$accent"
            note = "" if controllable(name) else "   [$text-muted]automatic[/]"
            bar = (f"[{colour}]{'█' * filled}[/]"
                   f"[$panel-lighten-2]{'░' * (BAR_WIDTH - filled)}[/]")
            try:
                self.query_one(f"#fn-bar-{index}", Static).update(
                    f"[$text-muted]{fan_label(name):<{LABEL_WIDTH}}[/]{bar} "
                    f"[b]{percent:3.0f}%[/b]{note}"
                )
            except Exception:
                pass

    # -- commands --------------------------------------------------------------

    def note(self, message: str) -> None:
        try:
            self.query_one("#fn-note", Static).update(message)
        except Exception:
            pass

    def read_custom(self, index: int) -> float | None:
        """The typed speed for a fan, as a percentage. None if unusable."""
        try:
            raw = self.query_one(f"#fn-in-{index}", Input).value.strip()
        except Exception:
            return None
        if not raw:
            self.note("[$error]Enter a speed first.[/]")
            return None
        try:
            percent = float(raw)
        except ValueError:
            self.note("[$error]Fan speed must be a number.[/]")
            return None
        if not 0 <= percent <= 100:
            self.note("[$error]Fan speed must be between 0 and 100%.[/]")
            return None
        self.note("")
        return percent

    def clear_custom(self, index: int) -> None:
        try:
            self.query_one(f"#fn-in-{index}", Input).value = ""
        except Exception:
            pass

    def index_of_input(self, widget_id: str) -> int | None:
        if not widget_id.startswith("fn-in-"):
            return None
        try:
            return int(widget_id.removeprefix("fn-in-"))
        except ValueError:
            return None

    def fan_at(self, index: int) -> str | None:
        return self.fans[index] if 0 <= index < len(self.fans) else None

    def nudged(self, index: int, delta: float) -> float:
        name = self.fan_at(index)
        current = self.speeds.get(name, 0.0) if name else 0.0
        return max(0.0, min(100.0, current + delta))
