"""Themes.

Textual resolves ``$name`` tokens in both stylesheets and content markup, so
panels reference semantic names and follow whatever theme is active. Alongside
the standard tokens each theme supplies domain colours for the temperature
series and the build-volume wireframe.
"""

from __future__ import annotations

from textual.theme import BUILTIN_THEMES, Theme

# Domain tokens every theme must define.
#   hot / hot-dim    extruder trace and its target line
#   bed / bed-dim    bed trace and its target line
#   vol-frame        build volume wireframe
#   vol-floor        bed plane and its grid
#   vol-head         toolhead marker
#   vol-drop         toolhead drop line and floor crosshair

OMINOUS = Theme(
    name="ominous",
    dark=True,
    background="#0b0809",
    surface="#141011",
    panel="#1c1618",
    primary="#a32638",
    secondary="#6d2f39",
    accent="#c4485a",
    foreground="#ddcfd2",
    success="#4f7d5e",
    warning="#c08238",
    error="#cf3b3b",
    variables={
        "hot": "#d1553d",
        "hot-dim": "#6b2c20",
        "bed": "#7b6f9c",
        "bed-dim": "#3d3652",
        "vol-frame": "#a32638",
        "vol-floor": "#5c4a52",
        "vol-head": "#e0a13c",
        "vol-drop": "#c4485a",
    },
)

MAINSAIL = Theme(
    name="mainsail",
    dark=True,
    background="#121212",
    surface="#1e1e1e",
    panel="#252525",
    primary="#2196f3",
    secondary="#1565c0",
    accent="#2196f3",
    foreground="#e0e0e0",
    success="#4caf50",
    warning="#ff9800",
    error="#d41216",
    variables={
        "hot": "#ff5722",
        "hot-dim": "#7f2c14",
        "bed": "#2196f3",
        "bed-dim": "#12507f",
        "vol-frame": "#ff9966",
        "vol-floor": "#9999cc",
        "vol-head": "#ffcc00",
        "vol-drop": "#cc6666",
    },
)

FORGE = Theme(
    name="forge",
    dark=True,
    background="#0d0c0a",
    surface="#17150f",
    panel="#1f1c14",
    primary="#c87f2a",
    secondary="#8a5a1f",
    accent="#e0a13c",
    foreground="#e2d8c3",
    success="#7d8c46",
    warning="#d8a13a",
    error="#c14a2b",
    variables={
        "hot": "#e0752a",
        "hot-dim": "#6e3a14",
        "bed": "#6f9ba8",
        "bed-dim": "#35505a",
        "vol-frame": "#c87f2a",
        "vol-floor": "#5a5240",
        "vol-head": "#f0d07a",
        "vol-drop": "#c14a2b",
    },
)

CUSTOM = {t.name: t for t in (OMINOUS, MAINSAIL, FORGE)}

# Built-in themes that suit a dark control panel. They lack the domain tokens,
# so those get filled in from a neutral set when one is selected.
BUILTIN_ALLOWED = [
    "textual-dark", "nord", "gruvbox", "dracula",
    "tokyo-night", "catppuccin-mocha", "monokai", "solarized-dark",
]

NEUTRAL_DOMAIN = {
    "hot": "#e06c4f",
    "hot-dim": "#6b2c20",
    "bed": "#6f9bd1",
    "bed-dim": "#2f4a6b",
    "vol-frame": "#d18f5a",
    "vol-floor": "#7c7c96",
    "vol-head": "#e8c25a",
    "vol-drop": "#c4685a",
}

DEFAULT_THEME = "ominous"


def all_theme_names() -> list[str]:
    return list(CUSTOM) + BUILTIN_ALLOWED


def register(app) -> None:
    """Register custom themes and backfill domain tokens on built-in ones."""
    for theme in CUSTOM.values():
        app.register_theme(theme)

    for name in BUILTIN_ALLOWED:
        base = BUILTIN_THEMES.get(name)
        if base is None:
            continue
        variables = dict(NEUTRAL_DOMAIN)
        variables.update(base.variables or {})
        app.register_theme(
            Theme(
                name=base.name,
                primary=base.primary,
                secondary=base.secondary,
                warning=base.warning,
                error=base.error,
                success=base.success,
                accent=base.accent,
                foreground=base.foreground,
                background=base.background,
                surface=base.surface,
                panel=base.panel,
                boost=base.boost,
                dark=base.dark,
                variables=variables,
            )
        )
