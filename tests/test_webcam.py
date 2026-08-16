"""Webcam URL handling and MJPEG frame extraction."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipper_tui.panels.webcam import (
    JPEG_END,
    JPEG_START,
    WebcamPanel,
    stream_url_for,
)

failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")


# The stream URL is derived from the snapshot URL by convention.
CASES = [
    ("http://host/webcam/?action=snapshot", "http://host/webcam/?action=stream"),
    ("http://host:8080/?action=snapshot", "http://host:8080/?action=stream"),
    ("http://host/webcam/snapshot", "http://host/webcam/stream"),
    # Nothing recognisable: leave it alone rather than mangle it.
    ("http://host/still.jpg", "http://host/still.jpg"),
]
for snapshot, expected in CASES:
    got = stream_url_for(snapshot)
    check(f"stream url for {snapshot}", got == expected, f"{got} != {expected}")

# Textual's MessagePump stores its own task as self._task. A widget that reuses
# that name never starts its reader, and stopping it cancels the widget's
# message pump instead.
import inspect  # noqa: E402

import textual.message_pump  # noqa: E402

source = inspect.getsource(sys.modules[WebcamPanel.__module__])
check("panel does not reuse Textual's _task attribute",
      "self._task" not in source,
      "rename it; MessagePump already owns self._task")
check("Textual really does own _task",
      "self._task" in inspect.getsource(textual.message_pump),
      "if this ever changes the guard above can go")


# Frames are split on JPEG markers rather than the multipart boundary.
def extract(buffer: bytearray) -> list[bytes]:
    frames = []
    while True:
        start = buffer.find(JPEG_START)
        if start < 0:
            break
        end = buffer.find(JPEG_END, start + 2)
        if end < 0:
            break
        frames.append(bytes(buffer[start:end + 2]))
        del buffer[:end + 2]
    return frames


one = JPEG_START + b"aaaa" + JPEG_END
two = JPEG_START + b"bbbbbb" + JPEG_END
stream = bytearray(b"--boundary\r\nheaders\r\n\r\n" + one +
                   b"\r\n--boundary\r\nheaders\r\n\r\n" + two)
got = extract(stream)
check("both frames recovered", got == [one, two], f"{got}")

partial = bytearray(b"--boundary\r\n" + JPEG_START + b"cccc")
check("incomplete frame is held back", extract(partial) == [])
partial += b"dd" + JPEG_END
check("frame completes on the next chunk",
      extract(partial) == [JPEG_START + b"ccccdd" + JPEG_END])

for f in failures:
    print("FAIL", f)
print("webcam: all checks passed" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
