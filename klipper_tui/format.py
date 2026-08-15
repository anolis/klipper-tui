"""Formatting helpers shared across panels."""

from __future__ import annotations


def duration(seconds: float | None) -> str:
    if not seconds or seconds < 0:
        return "--:--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def filesize(num: float | None) -> str:
    if not num:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def temp(current: float | None, target: float | None) -> str:
    cur = f"{current:.1f}" if current is not None else "--"
    if target:
        return f"[b]{cur}[/b]°C [#9e9e9e]/ {target:.0f}°C[/]"
    return f"[b]{cur}[/b]°C [#9e9e9e]/ off[/]"


def state_markup(state: str) -> str:
    colors = {
        "ready": "#4caf50",
        "printing": "#2196f3",
        "paused": "#ff9800",
        "complete": "#4caf50",
        "cancelled": "#ff9800",
        "error": "#D41216",
        "shutdown": "#D41216",
        "disconnected": "#D41216",
        "standby": "#9e9e9e",
    }
    color = colors.get(state.lower(), "#e0e0e0")
    return f"[{color} b]{state.upper()}[/]"
