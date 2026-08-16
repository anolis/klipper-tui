"""Is a widget actually on screen?

Show and Hide events are not enough on their own. A panel inside a tab that has
never been opened is never shown and never hidden, so an event-tracked flag
keeps whatever it was initialised to — which is how the toolhead view carried
on spinning, at half a core, inside a tab nobody had looked at.

A widget that occupies no area is not being drawn, whatever events it has or
has not received.
"""

from __future__ import annotations


def on_screen(widget) -> bool:
    region = getattr(widget, "region", None)
    if region is None:
        return False
    return region.width > 0 and region.height > 0
