"""CLI entry point."""

from __future__ import annotations

import argparse
import os

from .app import KlipperTUI


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="klipper-tui", description="Terminal UI for Klipper via Moonraker"
    )
    parser.add_argument(
        "host",
        nargs="?",
        default=os.environ.get("KLIPPER_HOST", "localhost"),
        help="Moonraker host (default: $KLIPPER_HOST or localhost)",
    )
    parser.add_argument(
        "-p", "--port", type=int,
        default=int(os.environ.get("KLIPPER_PORT", 7125)),
        help="Moonraker port (default: 7125)",
    )
    args = parser.parse_args()
    KlipperTUI(args.host, args.port).run()


if __name__ == "__main__":
    main()
