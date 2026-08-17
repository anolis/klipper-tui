"""How much longer, from two different points of view.

The slicer's figure is a prediction made before the print started. It knows the
whole job but nothing about this printer on this day — a speed override, a
slower first layer, a pause to change filament, a bed that takes a while to
come up, all of it passes it by. It is very good at the start, when there is
nothing else to go on, and drifts as the print diverges from the plan.

The measured figure is the opposite. It watches how fast the file is actually
being consumed and projects that forward. It knows nothing about what is left
to print — a job that ends in a slow dense top surface will finish later than
it says — but it does track what the machine is really doing, and it responds
to a speed change within a minute or so.

Neither is right. Showing both, and saying which is which, is more honest than
picking one and calling it the answer.
"""

from __future__ import annotations

from collections import deque

# How much history the measured rate is taken over. Long enough that a travel
# move or a pause between layers does not swing it, short enough to notice a
# speed override within a minute.
WINDOW = 180.0

# Below this the sample span is too short to divide by with a straight face.
MIN_SPAN = 20.0

# A print is not "progressing" if the file has barely moved; this keeps a
# paused job from claiming an absurd remaining time.
MIN_PROGRESS = 1e-5

# How many recent layer changes the layer rate is taken over. Layer times vary
# a lot — a tall thin section flies past, a wide one crawls — so a handful of
# them averages out the shape of the model without averaging away a genuine
# change of pace.
LAYER_HISTORY = 12


class Estimator:
    """Projects a finish time from how fast the file is actually being read."""

    def __init__(self, window: float = WINDOW) -> None:
        self.window = window
        # (monotonic seconds, fraction of the file consumed)
        self._samples: deque[tuple[float, float]] = deque()

    def reset(self) -> None:
        """A new job means the old rate says nothing about this one."""
        self._samples.clear()

    def record(self, now: float, progress: float) -> None:
        """Note the progress at a moment. Progress is 0..1."""
        if progress < 0 or progress > 1:
            return
        # A progress figure that has gone backwards means a different job, or
        # the same one restarted; either way the history is worthless.
        if self._samples and progress < self._samples[-1][1] - MIN_PROGRESS:
            self.reset()
        self._samples.append((now, progress))
        cutoff = now - self.window
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def rate(self) -> float | None:
        """Fraction of the file per second, over the recent window."""
        if len(self._samples) < 2:
            return None
        (t0, p0), (t1, p1) = self._samples[0], self._samples[-1]
        span = t1 - t0
        if span < MIN_SPAN:
            return None
        moved = p1 - p0
        if moved <= MIN_PROGRESS:
            return None
        return moved / span

    def remaining(self) -> float | None:
        """Seconds left at the rate of the last few minutes, or None."""
        rate = self.rate()
        if rate is None:
            return None
        progress = self._samples[-1][1]
        return max(0.0, (1.0 - progress) / rate)


def slicer_remaining(meta: dict, elapsed: float) -> float | None:
    """What the slicer thought was left, given how long we have been going."""
    total = (meta or {}).get("estimated_time")
    if not total or total <= 0:
        return None
    return max(0.0, total - elapsed)


def filament_remaining(stats: dict, meta: dict, elapsed: float) -> float | None:
    """Time left by extrusion, which tracks the work rather than the clock."""
    used = (stats or {}).get("filament_used") or 0
    total = (meta or {}).get("filament_total") or 0
    if used > 0 and total > 0 and used < total:
        return elapsed * (total / used - 1)
    return None


def best(measured: float | None, slicer: float | None,
         filament: float | None, elapsed: float,
         progress: float) -> tuple[float, str]:
    """The figure to lead with, and one word for where it came from.

    The slicer leads early, because a measured rate taken over the first
    minute of a print is mostly the heat-up. Once there is a real rate to go
    on, that leads instead: it is the one that reacts when the machine does
    something the slicer did not plan for.
    """
    if measured is not None and progress > 0.05:
        return measured, "measured"
    if slicer is not None:
        return slicer, "slicer"
    if measured is not None:
        return measured, "measured"
    if filament is not None:
        return filament, "filament"
    if progress > 0.02:
        return max(0.0, elapsed * (1 / progress - 1)), "file"
    return 0.0, ""


class LayerRate:
    """How fast layers are actually going by, and what that implies.

    Layers are the unit the work happens in, and the unit people think in, so
    a rate expressed in layers a minute is easier to sanity-check than one in
    bytes a second. It is also less easily fooled: gcode density varies wildly
    between a sparse infill layer and a dense top surface, so file position
    can crawl while the print is moving along, and vice versa.

    Only layer *changes* are timed. Sampling the current layer every quarter
    second would mostly measure how long we have been sitting on one layer.
    """

    def __init__(self, history: int = LAYER_HISTORY) -> None:
        self.history = history
        self._changes: deque[tuple[float, int]] = deque(maxlen=history)
        self._current: int | None = None
        self.total: int | None = None

    def reset(self) -> None:
        self._changes.clear()
        self._current = None
        self.total = None

    def record(self, now: float, layer: int | None, total: int | None) -> None:
        if layer is None or total is None or total <= 0:
            return
        # Going backwards means a different job, or the same one restarted.
        if self._current is not None and layer < self._current:
            self.reset()
        self.total = total
        if layer != self._current:
            self._current = layer
            self._changes.append((now, layer))

    @property
    def current(self) -> int | None:
        return self._current

    def per_minute(self) -> float | None:
        """Layers a minute over the recent history, or None if unknown."""
        if len(self._changes) < 2:
            return None
        (t0, l0), (t1, l1) = self._changes[0], self._changes[-1]
        span = t1 - t0
        if span <= 0 or l1 <= l0:
            return None
        return (l1 - l0) / span * 60.0

    def remaining(self) -> float | None:
        """Seconds left at the current layer rate."""
        rate = self.per_minute()
        if rate is None or self.total is None or self._current is None:
            return None
        left = self.total - self._current
        if left <= 0:
            return 0.0
        return left / rate * 60.0
