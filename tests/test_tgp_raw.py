"""The raw-RGB kitty transmission must be a well formed graphics command.

Nothing here talks to a terminal: the escape stream is captured and parsed, so
a mistake shows up as a failed test rather than a corrupted screen.
"""

import base64
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The patch declines on an ssh session, and CI may look like one.
os.environ["KLIPPER_TUI_RAW_TGP"] = "1"
os.environ.pop("SSH_CONNECTION", None)

from klipper_tui.panels import webcam  # noqa: E402  (import applies the patch)

if not webcam.AVAILABLE:
    print("skipped: image rendering unavailable")
    sys.exit(0)

from PIL import Image as PILImage  # noqa: E402
from textual_image.renderable import tgp  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


def capture(fn):
    """Everything written to stdout, including writes that bypass sys.stdout.

    The graphics commands go to the file descriptor directly, so
    redirect_stdout does not see them.
    """
    sys.stdout.flush()
    saved = os.dup(1)
    with tempfile.TemporaryFile(mode="w+") as sink:
        os.dup2(sink.fileno(), 1)
        try:
            fn()
            sys.stdout.flush()
        finally:
            os.dup2(saved, 1)
            os.close(saved)
        sink.seek(0)
        return sink.read()


if not getattr(tgp, "_klipper_tui_raw", False):
    failures.append("the raw transmission patch did not apply")

WIDTH, HEIGHT = 40, 30
source = PILImage.new("RGB", (WIDTH, HEIGHT), (10, 20, 30))
renderable = tgp.Image(source)

stream = capture(lambda: renderable._send_image_to_terminal(WIDTH, HEIGHT))

commands = re.findall(r"\x1b_G([^;]*);([^\x1b]*)\x1b\\", stream)
if not commands:
    failures.append(f"no graphics commands emitted (got {stream[:80]!r})")
else:
    first_keys = dict(pair.split("=", 1) for pair in commands[0][0].split(","))
    check("format is raw RGB", first_keys.get("f"), "24")
    check("pixel width", first_keys.get("s"), str(WIDTH))
    check("pixel height", first_keys.get("v"), str(HEIGHT))
    check("quiet", first_keys.get("q"), "2")

    # Every chunk but the last says more is coming.
    more = [dict(pair.split("=", 1) for pair in keys.split(","))["m"]
            for keys, _ in commands]
    check("continuation flags", more, ["1"] * (len(commands) - 1) + ["0"])

    ids = {dict(pair.split("=", 1) for pair in keys.split(","))["i"]
           for keys, _ in commands}
    check("one image id for the whole transfer", len(ids), 1)

    # Later chunks must not repeat the format keys.
    for index, (keys, _) in enumerate(commands[1:], start=1):
        parsed = dict(pair.split("=", 1) for pair in keys.split(","))
        if "f" in parsed or "s" in parsed or "v" in parsed:
            failures.append(f"chunk {index} repeats the format keys")

    payload = "".join(body for _, body in commands)
    for _, body in commands[:-1]:
        if len(body) != 4096:
            failures.append(f"chunk is {len(body)} bytes, wanted 4096")
    try:
        decoded = base64.standard_b64decode(payload)
    except Exception as error:
        failures.append(f"payload is not valid base64: {error}")
        decoded = b""
    check("payload is width*height*3 bytes", len(decoded), WIDTH * HEIGHT * 3)
    check("first pixel survives the trip", decoded[:3], bytes((10, 20, 30)))


# A greyscale or palette frame has to be converted, not sent as fewer bytes.
grey = tgp.Image(PILImage.new("L", (8, 8), 128))
grey_stream = capture(lambda: grey._send_image_to_terminal(8, 8))
body = "".join(re.findall(r"\x1b_G[^;]*;([^\x1b]*)\x1b\\", grey_stream))
check("greyscale is widened to RGB",
      len(base64.standard_b64decode(body)), 8 * 8 * 3)


if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
