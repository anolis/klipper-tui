"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os

from .app import KlipperTUI


def main() -> None:
    # textual-image probes the terminal for its cell size and logs a warning
    # with a full traceback when the terminal does not answer (gnome-terminal
    # does not). It falls back to VT340 sizes and works fine, so the noise on
    # exit is not worth showing.
    logging.getLogger("textual_image").setLevel(logging.ERROR)

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
    parser.add_argument(
        "--webcam-url",
        default=os.environ.get("KLIPPER_WEBCAM_URL"),
        help="MJPEG snapshot URL (default: http://<host>/webcam/?action=snapshot)",
    )
    parser.add_argument(
        "--render",
        choices=["auto", "sixel", "tgp", "halfcell", "unicode"],
        default=os.environ.get("KLIPPER_RENDER", "auto"),
        help="Webcam renderer. 'auto' detects terminal support; force 'sixel' "
             "if detection fails, 'unicode'/'halfcell' for terminals without "
             "graphics support (e.g. gnome-terminal).",
    )
    args = parser.parse_args()
    KlipperTUI(args.host, args.port, args.webcam_url, args.render).run()


if __name__ == "__main__":
    main()
