"""A terminal UI for Klipper 3D printers."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read the installed version rather than repeating it here, where it drifts
    # away from pyproject.toml the first time one of the two is bumped alone.
    __version__ = version("klipper-tui")
except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.0.0"
