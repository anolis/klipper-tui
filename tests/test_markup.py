"""Guards against markup-dialect mistakes.

RichLog uses Rich markup; Static uses Textual content markup. A `$token` sent
to the former raises MarkupError at runtime, which is only noticed when that
exact line is written.
"""
import asyncio
import sys

sys.path.insert(0, "/home/anolis/repos/klipper-tui")

from klipper_tui.app import KlipperTUI
from klipper_tui.panels.console import ConsolePanel
from klipper_tui.theming import all_theme_names


async def main() -> int:
    failures = []
    app = KlipperTUI("127.0.0.1")  # no printer needed; nothing is sent
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.5)
        console = app.query_one(ConsolePanel)
        for theme in all_theme_names():
            app.theme = theme
            await pilot.pause(0.05)
            try:
                console.write_echo("G28")
                console.write_system("heating to 250C")
                console.write_response("ok")
                console.write_response("// echo: probe at 1.5")
                console.write_response("!! Move out of range")
                console.write_response("value [not a tag] here")
            except Exception as exc:
                failures.append(f"{theme}: {type(exc).__name__}: {exc}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(all_theme_names()) - len(failures)}/{len(all_theme_names())} themes ok")
    return 1 if failures else 0


sys.exit(asyncio.run(main()))
