"""Nothing in a panel may shadow Textual's Widget API.

This has bitten three times: `self._task` collided with MessagePump's own task
so a frame reader never started, `self.layers` collided with the read-only CSS
layers property, and `_render` collided with Widget's renderer and was called
with the wrong arguments. Each one only surfaced at runtime, on the code path
that happened to touch it.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual.screen import Screen
from textual.widget import Widget

# Names we mean to define: Textual's extension points and message handlers.
INTENTIONAL = {
    "compose", "render", "on_mount", "on_unmount", "on_show", "on_resize",
    "on_key", "on_click", "on_input_changed", "on_input_submitted",
    "on_button_pressed", "BINDINGS", "CSS", "CSS_PATH", "DEFAULT_CSS",
    "COMPONENT_CLASSES", "can_focus", "can_focus_children",
}

def _reserved_names() -> set[str]:
    """Everything Textual already owns on a widget.

    Class attributes are not enough: MessagePump sets instance attributes in
    its constructor — self._task among them — which never show up in dir() of
    the class, and that is exactly the collision that cost the most to find.
    """
    names = set(dir(Widget)) | set(dir(Screen))
    for cls in (Widget, Screen):
        try:
            names |= set(vars(cls()))
        except Exception:
            pass
    return {name for name in names if not name.startswith("__")}


RESERVED = _reserved_names() - INTENTIONAL

failures = []
panels = sorted((Path(__file__).resolve().parent.parent
                 / "klipper_tui" / "panels").glob("*.py"))
checked = 0

for path in panels:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        checked += 1
        for item in node.body:
            # Methods defined on the class.
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name in RESERVED:
                    failures.append(
                        f"{path.name}:{node.name}.{item.name}() shadows "
                        f"Textual's Widget API")
        # Attributes assigned anywhere inside the class body.
        for sub in ast.walk(node):
            target = None
            if isinstance(sub, ast.Assign) and sub.targets:
                target = sub.targets[0]
            elif isinstance(sub, ast.AnnAssign):
                target = sub.target
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr in RESERVED):
                failures.append(
                    f"{path.name}:{node.name}.{target.attr} shadows "
                    f"Textual's Widget API")

for f in sorted(set(failures)):
    print("FAIL", f)
print(f"checked {checked} classes across {len(panels)} files")
print("no shadowing" if not failures else f"{len(set(failures))} collisions")
sys.exit(1 if failures else 0)
