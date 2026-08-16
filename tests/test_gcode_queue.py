"""Slow commands must not stall the interface.

Awaiting a gcode call inside a Textual message handler blocks the message
pump, which froze the whole UI for the length of a homing move.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.app import KlipperTUI
from textual.widgets import Button, TabbedContent

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


async def main() -> int:
    # No printer needed; nothing here reaches the network.
    app = KlipperTUI("127.0.0.1", port=1)
    async with app.run_test(size=(100, 42)) as pilot:
        await pilot.pause(0.6)

        sent = []

        async def slow(script, timeout=15.0):
            sent.append(script)
            await asyncio.sleep(3.0)
            return {}

        app.client.gcode = slow
        tabs = app.query_one(TabbedContent)
        tabs.active = "move"
        await pilot.pause(0.4)

        started = time.monotonic()
        app.query_one("#th-home-all", Button).press()
        elapsed = time.monotonic() - started
        check("press returns immediately", elapsed < 0.5, f"took {elapsed:.2f}s")

        for tab in ("dashboard", "graph", "files"):
            tabs.active = tab
            await pilot.pause(0.2)
            check(f"can reach {tab} mid-command", tabs.active == tab)

        check("command was queued", sent == ["G28"], f"{sent}")

        await pilot.pause(3.2)
        check("queue drains", app._gcode_queue.empty())

        # Queueing must not reorder commands.
        order = []

        async def record(script, timeout=15.0):
            order.append(script)
            await asyncio.sleep(0.1)
            return {}

        app.client.gcode = record
        for command in ("M117 a", "M117 b", "M117 c"):
            await app.send(command, echo=False)
        await pilot.pause(1.5)
        check("order preserved", order == ["M117 a", "M117 b", "M117 c"],
              f"{order}")

    for f in failures:
        print("FAIL", f)
    print("gcode queue: all checks passed" if not failures
          else f"{len(failures)} failed")
    return 1 if failures else 0


sys.exit(asyncio.run(main()))
