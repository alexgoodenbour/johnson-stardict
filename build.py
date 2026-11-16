#!/usr/bin/env python3
"""Build a StarDict edition of Johnson's Dictionary (1755) for KOReader & co.

    python3 build.py            # download sources (once), build into dist/

Requires Python 3.10+ and lxml.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from lxml import etree

from johnson import modern, parse, sources, stardict

ROOT = Path(__file__).resolve().parent
BASENAME = "johnson1755"

INFO = {
    "bookname": "Johnson's Dictionary (1755)",
    "author": "Samuel Johnson",
    "website": "https://leme.library.utoronto.ca/lexicons/1345/",
    "description": (
        "Samuel Johnson, A Dictionary of the English Language, first folio edition "
        "(London, 1755).<br>"
        "Text from Lexicons of Early Modern English (LEME), ed. Ian Lancashire, "
        "https://leme.library.utoronto.ca (lexicon 1345, https://hdl.handle.net/1807/124274), "
        "licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). "
        "Converted to StarDict, with sense divisions, verse layout and citations "
        "recovered from the transcription.<br>"
        "Inflected lookup forms from the English Speller Database, "
        "Copyright 2000-2026 by Kevin Atkinson; see LICENSE.txt."
    ),
    "lang": "en-en",
}


def assemble(entries: list[parse.Entry], esdb: modern.ESDB):
    """Merge entries sharing a headword and compute all synonyms."""
    articles: dict[str, list[str]] = defaultdict(list)
    alt_keys: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        primary = e.keys[0]
        articles[primary].append(f'<div class="entry">{e.html}</div>')
        for k in e.keys[1:]:
            alt_keys[k].add(primary)

    # every lookup key -> the articles it should open
    targets: dict[str, set[str]] = {k: {k} for k in articles}
    for k, primaries in alt_keys.items():
        targets.setdefault(k, set()).update(primaries)

    synonyms: dict[str, set[str]] = defaultdict(set)
    for k, ts in targets.items():
        synonyms[k].update(t for t in ts if t != k)
    for word, keys in modern.build_synonyms(set(targets), esdb).items():
        for k in keys:
            synonyms[word].update(t for t in targets[k] if t != word)
    synonyms = {w: ts for w, ts in synonyms.items() if ts}
    return {k: "".join(v) for k, v in articles.items()}, synonyms


def check(ifo: Path) -> None:
    """Read the result back, validate its structure and spot-check lookups."""
    info, entries, syns, lookup = stardict.read(ifo)
    print(f"check: {info['wordcount']} headwords, {info['synwordcount']} synonyms")

    keys = [stardict.sort_key(w) for w, _, _ in entries]
    assert all(a < b for a, b in zip(keys, keys[1:])), ".idx not in StarDict order"
    skeys = [stardict.sort_key(s) for s, _ in syns]
    assert all(a <= b for a, b in zip(skeys, skeys[1:])), ".syn not in StarDict order"
    assert all(0 <= i < len(entries) for _, i in syns), ".syn points outside .idx"

    dz = stardict.DictzipReader(Path(str(ifo.with_suffix("")) + ".dict.dz"))
    full = gzip.decompress(dz.raw)  # also verifies the gzip CRC
    for w, off, size in entries:
        article = dz.read(off, size)
        assert article == full[off:off + size], f"dictzip random access broken at {w!r}"
        etree.fromstring(b"<root>" + article + b"</root>")  # well-formed markup

    expectations = {
        "lexicographer": "lexicographer",
        "Abandoned": "abandon",     # inflection, capitalised as at a sentence start
        "mice": "mouse",
        "colors": "colour",         # US spelling of a lemma
        "oats": "oats",
        "abby": "abbey",            # Johnson's own alternative spelling
        "aenigma": "ænigma",        # ligature folded to ASCII
    }
    failed = False
    for query, want in expectations.items():
        got = [w for w, _ in lookup(query)]
        ok = want in got
        failed |= not ok
        print(f"  {'ok ' if ok else 'BAD'} {query!r:18} -> {got}")
    if failed:
        raise SystemExit("lookup check failed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", type=Path, default=ROOT / "sources")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    src = sources.fetch(args.sources)
    print("parsing Johnson ...", file=sys.stderr)
    entries = parse.parse(src["johnson1755.xml"], ROOT / "data")
    print("loading ESDB ...", file=sys.stderr)
    esdb = modern.ESDB(src["scowl-pre.txt"])
    articles, synonyms = assemble(entries, esdb)

    out = args.out / BASENAME
    if out.exists():
        shutil.rmtree(out)
    paths = stardict.write(out, BASENAME, articles, synonyms, INFO | {"date": args.date})
    shutil.copy(ROOT / "data" / "johnson.css", out / f"{BASENAME}.css")
    shutil.copy(ROOT / "data" / "LICENSE-dictionary.txt", out / "LICENSE.txt")
    print(f"{len(entries)} entries -> {len(articles)} headwords, "
          f"{sum(len(v) for v in synonyms.values())} synonym links", file=sys.stderr)

    check(paths["ifo"])

    zpath = args.out / f"{BASENAME}-stardict.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.iterdir()):
            z.write(f, f"{BASENAME}/{f.name}")
    print(f"wrote {out}/ and {zpath}")


if __name__ == "__main__":
    main()
