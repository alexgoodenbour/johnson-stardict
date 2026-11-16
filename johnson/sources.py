"""Download and verify the upstream source files.

Both sources are pinned to exact content by SHA-256 so that a build is
reproducible; if upstream changes, the checksum check fails loudly instead of
silently producing a different dictionary.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

SOURCES = {
    # Lexicons of Early Modern English, ed. Ian Lancashire. TEI-style XML
    # transcription of Johnson's 1755 folio, deposited in TSpace
    # (https://hdl.handle.net/1807/124274). Licensed CC BY 4.0.
    "johnson1755.xml": {
        "url": "https://utoronto.scholaris.ca/server/api/core/bitstreams/"
               "d1c03246-eafa-4d0f-8204-65e100b8db78/content",
        "sha256": "e7d9690ce31509438143a34f4b0b16a6947e0d17786cddec1951924787122cee",
    },
    # English Speller Database (ESDB, formerly SCOWL) by Kevin Atkinson.
    # Used only to map inflected forms (and US/UK variants) onto Johnson's
    # headwords. MIT-like license (see data/LICENSE-dictionary.txt).
    "scowl-pre.txt": {
        "url": "https://raw.githubusercontent.com/en-wl/wordlist/"
               "1e5b7d3a72f47a71da5d28686c1dd4b397178485/data/scowl-pre.txt",
        "sha256": "a5fe3f11682a6ab9d31f2ea2a185833b1a01be7af83409c671bd0756a870f6c7",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(dest: Path) -> dict:
    """Ensure every source file exists in `dest` with the expected checksum."""
    dest.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, info in SOURCES.items():
        path = dest / name
        if not path.exists():
            print(f"downloading {name} ...", file=sys.stderr)
            tmp = path.with_suffix(path.suffix + ".part")
            req = urllib.request.Request(info["url"], headers={"User-Agent": "johnson-stardict-build"})
            with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.rename(path)
        if sha256(path) != info["sha256"]:
            raise SystemExit(
                f"checksum mismatch for {path}\n"
                f"  expected {info['sha256']}\n  got      {sha256(path)}\n"
                "Upstream data changed; delete the file to re-download, then update the pin."
            )
        paths[name] = path
    return paths
