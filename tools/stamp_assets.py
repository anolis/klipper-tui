"""Stamp app.js and styles.css with a content hash in index.html.

GitHub Pages serves everything with `cache-control: max-age=600` and caches
each file independently, so for ten minutes after a deploy a browser can hold
a fresh index.html alongside a stale app.js. That is invisible until a change
renames something both files refer to — then the page half-works, which is
worse than failing outright.

A query string derived from the file's contents makes the pair inseparable:
new JS means a new URL, so the HTML that mentions it can never be served with
the old one.

Run this after touching app.js or styles.css, before committing:

    python3 tools/stamp_assets.py
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
ASSETS = ("app.js", "styles.css")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def main() -> int:
    html = PAGE.read_text()
    original = html

    for name in ASSETS:
        path = ROOT / name
        if not path.exists():
            print(f"missing {name}", file=sys.stderr)
            return 1
        stamp = digest(path)
        # Matches the bare name and any previous stamp.
        pattern = re.compile(rf'(["\'])({re.escape(name)})(\?v=[0-9a-f]+)?\1')
        html, count = pattern.subn(rf'\g<1>{name}?v={stamp}\g<1>', html)
        if not count:
            print(f"{name} is not referenced by index.html", file=sys.stderr)
            return 1
        print(f"{name:12} -> ?v={stamp}  ({count} reference"
              f"{'s' if count != 1 else ''})")

    if html == original:
        print("already up to date")
        return 0
    PAGE.write_text(html)
    print("index.html updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
