"""Cancel individual objects from a running plate.

Only useful when the printer has [exclude_object] and the gcode was sliced with
object labelling, so the panel says so rather than showing an empty list.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static


def object_name(entry) -> str:
    """Objects come through as dicts with a name, or occasionally as strings."""
    if isinstance(entry, dict):
        return str(entry.get("name") or entry.get("id") or "?")
    return str(entry)


class ObjectsPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(id="objects-panel", classes="panel")
        self.objects: list[str] = []
        self.excluded: set[str] = set()
        self.current: str | None = None
        self.supported = False

    def compose(self) -> ComposeResult:
        yield Label("Objects", classes="panel-title")
        yield Static("", id="ob-note", classes="dim")
        yield Vertical(id="ob-list")

    def update_status(self, status: dict) -> None:
        section = status.get("exclude_object")
        self.supported = section is not None
        names = [object_name(o) for o in (section or {}).get("objects", [])]
        excluded = {object_name(o)
                    for o in (section or {}).get("excluded_objects", [])}
        current = (section or {}).get("current_object")
        current = object_name(current) if current else None

        changed = (names != self.objects or excluded != self.excluded
                   or current != self.current)
        self.objects, self.excluded, self.current = names, excluded, current
        if changed:
            self._rebuild()

    def _rebuild(self) -> None:
        try:
            container = self.query_one("#ob-list", Vertical)
            note = self.query_one("#ob-note", Static)
        except Exception:
            return
        container.remove_children()

        if not self.supported:
            note.update(
                "[$text-muted]This printer has no [/][b]\\[exclude_object][/b]"
                "[$text-muted] section, so objects cannot be cancelled "
                "individually.[/]"
            )
            return
        if not self.objects:
            note.update(
                "[$text-muted]No objects in the current job. The gcode has to "
                "be sliced with object labelling turned on.[/]"
            )
            return

        remaining = len(self.objects) - len(self.excluded)
        note.update(
            f"[$text-muted]{remaining} of {len(self.objects)} still "
            f"printing. Cancelling one cannot be undone.[/]"
        )

        rows = []
        for index, name in enumerate(self.objects):
            excluded = name in self.excluded
            if excluded:
                label, mark = "cancelled", "[$text-muted]"
            elif name == self.current:
                label, mark = "printing now", "[$accent]"
            else:
                label, mark = "queued", "[$foreground]"
            button = Button("Cancel", id=f"ob-cancel-{index}",
                            classes="-danger")
            button.disabled = excluded
            rows.append(Horizontal(
                button,
                Static(f"{mark}{name}[/]  [$text-muted]{label}[/]",
                       classes="setting-label"),
                classes="btn-row",
            ))
        container.mount(*rows)

    def object_at(self, index: int) -> str | None:
        return self.objects[index] if 0 <= index < len(self.objects) else None
