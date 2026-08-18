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


class Estimator:
    """Projects a finish time from how fast the file is actually being read."""

    def __init__(self, window: float = WINDOW) -> None:
        self.window = window
        # (monotonic seconds, fraction of the file consumed)
        self._samples: deque[tuple[float, float]] = deque()
        # Fraction of the file per second the slicer's estimate implies, used
        # until enough of the print has been watched to have an opinion.
        self.prior: float | None = None

    def reset(self) -> None:
        """A new job means the old rate says nothing about this one."""
        self._samples.clear()
        self.prior = None

    def seed(self, total_seconds: float | None) -> None:
        """Start from the pace the slicer's estimate implies.

        The whole file in total_seconds is a rate, and it is a much better
        first guess than nothing. Without it the first three minutes of every
        print have no measured figure at all, and the minute after that swings
        about while the window fills.

        It is a starting point, not an answer: real samples take over as they
        accumulate, in proportion to how much of the window they cover.
        """
        if not total_seconds or total_seconds <= 0:
            self.prior = None
            return
        self.prior = 1.0 / total_seconds

    def record(self, now: float, progress: float) -> None:
        """Note the progress at a moment. Progress is 0..1."""
        if progress < 0 or progress > 1:
            return
        # A progress figure that has gone backwards means a different job, or
        # the same one restarted; either way the history is worthless.
        if self._samples and progress < self._samples[-1][1] - MIN_PROGRESS:
            self.reset()
        self._samples.append((now, progress))
        # Keep the last sample that predates the cutoff, so the span really
        # covers the window rather than falling a fraction short of it.
        # Dropping everything older left the span permanently just under, and
        # a share of 0.999 never reads as a full window.
        cutoff = now - self.window
        while len(self._samples) > 2 and self._samples[1][0] <= cutoff:
            self._samples.popleft()

    def measured_rate(self) -> tuple[float | None, float]:
        """The rate from observation alone, and the span it was taken over."""
        if len(self._samples) < 2:
            return None, 0.0
        (t0, p0), (t1, p1) = self._samples[0], self._samples[-1]
        span = t1 - t0
        if span < MIN_SPAN:
            return None, span
        moved = p1 - p0
        if moved <= MIN_PROGRESS:
            return None, span
        return moved / span, span

    def measured_share(self) -> float:
        """How much of the blended rate is observation rather than the seed.

        Simply how full the averaging window is: three minutes of samples is
        1.0, ninety seconds is 0.5. It is the weight used in the blend, not a
        confidence in any statistical sense — it says nothing about whether
        the observed rate is steady, nor whether the two estimates agree, only
        how much of the answer stopped being a guess.
        """
        if self.prior is None:
            return 1.0
        _, span = self.measured_rate()
        return max(0.0, min(1.0, span / self.window))

    def rate(self) -> float | None:
        """Fraction of the file per second.

        Observation once there is enough of it, the slicer's implied pace
        before that, and a weighted blend in between so the figure does not
        jump when measurement takes over.
        """
        measured, span = self.measured_rate()
        if measured is None:
            return self.prior
        if self.prior is None:
            return measured
        weight = self.measured_share()
        return measured * weight + self.prior * (1.0 - weight)

    def remaining(self) -> float | None:
        """Seconds left at the rate of the last few minutes, or None."""
        rate = self.rate()
        if rate is None or rate <= 0:
            return None
        progress = self._samples[-1][1] if self._samples else 0.0
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

