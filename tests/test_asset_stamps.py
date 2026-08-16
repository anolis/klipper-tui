"""index.html must reference the app.js and styles.css it was built against.

GitHub Pages caches each file independently for ten minutes, so a stale script
can be paired with fresh markup. The stamp in the query string makes that
impossible — but only while it matches, so this fails the build when someone
edits an asset and forgets to run tools/stamp_assets.py.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures = []

html = (ROOT / "index.html").read_text()

for name in ("app.js", "styles.css"):
    path = ROOT / name
    if not path.exists():
        failures.append(f"{name} is missing")
        continue
    want = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    found = re.findall(rf'{re.escape(name)}\?v=([0-9a-f]+)', html)
    if not found:
        failures.append(
            f"{name} is referenced without a ?v= stamp; "
            f"run python3 tools/stamp_assets.py")
    elif found[0] != want:
        failures.append(
            f"{name} stamp is {found[0]}, contents hash to {want}; "
            f"run python3 tools/stamp_assets.py")

    # A bare reference alongside a stamped one would still be cacheable.
    bare = re.findall(rf'["\']{re.escape(name)}["\']', html)
    if bare:
        failures.append(f"{name} is also referenced without a stamp")

if failures:
    print("FAIL")
    for line in failures:
        print("  " + line)
    sys.exit(1)
print("ok")
