"""Minimal StarDict writer and reader (with dictzip compression).

Format reference: https://github.com/huzheng001/stardict-3/blob/master/dict/doc/StarDictFileFormat
dictzip:          dictzip(1) from dictd -- a gzip file whose FEXTRA "RA"
                  field lists independently decompressible chunks.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

_UPPER = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_LOWER = bytes.maketrans(_UPPER, _UPPER.lower())


def sort_key(word: str) -> tuple[bytes, bytes]:
    """StarDict's stardict_strcmp: g_ascii_strcasecmp, ties broken by strcmp."""
    b = word.encode("utf-8")
    return b.translate(_ASCII_LOWER), b


# --------------------------------------------------------------------------
# dictzip

CHUNK = 58315  # dictzip's default chunk length


def dictzip(data: bytes, path: Path, name: str = "") -> None:
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b""]
    sizes, body = [], []
    for i, chunk in enumerate(chunks):
        flush = zlib.Z_FINISH if i == len(chunks) - 1 else zlib.Z_FULL_FLUSH
        out = comp.compress(chunk) + comp.flush(flush)
        sizes.append(len(out))
        body.append(out)
    if max(sizes) > 0xFFFF or len(chunks) > 32000:
        raise ValueError("data too large for dictzip")

    ra = struct.pack("<HHH", 1, CHUNK, len(chunks)) + b"".join(struct.pack("<H", s) for s in sizes)
    extra = b"RA" + struct.pack("<H", len(ra)) + ra
    flags = 0x04 | (0x08 if name else 0)  # FEXTRA, FNAME
    header = struct.pack("<BBBBIBB", 0x1F, 0x8B, 8, flags, 0, 2, 3)  # mtime 0: reproducible
    header += struct.pack("<H", len(extra)) + extra
    if name:
        header += name.encode("latin-1") + b"\0"
    trailer = struct.pack("<II", zlib.crc32(data) & 0xFFFFFFFF, len(data) & 0xFFFFFFFF)
    path.write_bytes(header + b"".join(body) + trailer)


class DictzipReader:
    """Random access into a .dict.dz, the way StarDict readers do it."""

    def __init__(self, path: Path):
        self.raw = path.read_bytes()
        assert self.raw[:3] == b"\x1f\x8b\x08" and self.raw[3] & 0x04, "not a dictzip file"
        xlen = struct.unpack_from("<H", self.raw, 10)[0]
        extra = self.raw[12:12 + xlen]
        assert extra[:2] == b"RA"
        ver, self.chlen, count = struct.unpack_from("<HHH", extra, 4)
        assert ver == 1
        self.sizes = struct.unpack_from(f"<{count}H", extra, 10)
        pos = 12 + xlen
        if self.raw[3] & 0x08:
            pos = self.raw.index(b"\0", pos) + 1
        self.offsets = []
        for s in self.sizes:
            self.offsets.append(pos)
            pos += s

    def _chunk(self, i: int) -> bytes:
        d = zlib.decompressobj(-15)
        return d.decompress(self.raw[self.offsets[i]:self.offsets[i] + self.sizes[i]])

    def read(self, offset: int, size: int) -> bytes:
        first, last = offset // self.chlen, (offset + size - 1) // self.chlen
        buf = b"".join(self._chunk(i) for i in range(first, last + 1))
        start = offset - first * self.chlen
        return buf[start:start + size]


# --------------------------------------------------------------------------

def write(out_dir: Path, basename: str, articles: dict[str, str],
          synonyms: dict[str, set[str]], info: dict[str, str]) -> dict[str, Path]:
    """Write <basename>.ifo/.idx/.dict.dz/.syn.

    articles: {headword: html}; synonyms: {alternative word: {headword, ...}}.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    words = sorted(articles, key=sort_key)
    for w in words:
        if len(w.encode("utf-8")) >= 256 or "\0" in w:
            raise ValueError(f"invalid headword {w!r}")
    index_of = {w: i for i, w in enumerate(words)}

    data, idx = bytearray(), bytearray()
    for w in words:
        body = articles[w].encode("utf-8")
        idx += w.encode("utf-8") + b"\0" + struct.pack(">II", len(data), len(body))
        data += body

    syn_records = sorted(
        ((s, index_of[t]) for s, targets in synonyms.items() for t in targets
         if len(s.encode("utf-8")) < 256),
        key=lambda r: (sort_key(r[0]), r[1]))
    syn = bytearray()
    for s, i in syn_records:
        syn += s.encode("utf-8") + b"\0" + struct.pack(">I", i)

    paths = {
        "ifo": out_dir / f"{basename}.ifo",
        "idx": out_dir / f"{basename}.idx",
        "dict": out_dir / f"{basename}.dict.dz",
        "syn": out_dir / f"{basename}.syn",
    }
    paths["idx"].write_bytes(idx)
    paths["syn"].write_bytes(syn)
    dictzip(bytes(data), paths["dict"], f"{basename}.dict")

    fields = {
        "version": "3.0.0",
        "bookname": info["bookname"],
        "wordcount": str(len(words)),
        "synwordcount": str(len(syn_records)),
        "idxfilesize": str(len(idx)),
        "sametypesequence": "h",
    }
    fields.update({k: v for k, v in info.items() if k != "bookname"})
    for k, v in fields.items():
        if "\n" in v:
            raise ValueError(f".ifo field {k} must be a single line")
    ifo = "StarDict's dict ifo file\n" + "".join(f"{k}={v}\n" for k, v in fields.items())
    paths["ifo"].write_text(ifo, encoding="utf-8")
    return paths


def read(ifo_path: Path):
    """Load a StarDict dictionary back.

    Returns (ifo fields, [(headword, offset, size)], [(synonym, index)], lookup).
    """
    base = ifo_path.with_suffix("")
    ifo = dict(line.split("=", 1) for line in ifo_path.read_text("utf-8").splitlines()[1:] if "=" in line)
    idx_raw = base.with_suffix(".idx").read_bytes()
    assert len(idx_raw) == int(ifo["idxfilesize"])
    entries, pos = [], 0
    while pos < len(idx_raw):
        end = idx_raw.index(b"\0", pos)
        off, size = struct.unpack_from(">II", idx_raw, end + 1)
        entries.append((idx_raw[pos:end].decode("utf-8"), off, size))
        pos = end + 9
    assert len(entries) == int(ifo["wordcount"])
    syns, pos = [], 0
    syn_raw = base.with_suffix(".syn").read_bytes() if base.with_suffix(".syn").exists() else b""
    while pos < len(syn_raw):
        end = syn_raw.index(b"\0", pos)
        (i,) = struct.unpack_from(">I", syn_raw, end + 1)
        syns.append((syn_raw[pos:end].decode("utf-8"), i))
        pos = end + 5
    assert len(syns) == int(ifo.get("synwordcount", 0))
    dz = DictzipReader(Path(str(base) + ".dict.dz"))

    def lookup(word: str) -> list[tuple[str, str]]:
        """Case-insensitive exact lookup through headwords and synonyms."""
        key = sort_key(word)[0]
        hits = [i for i, (w, _, _) in enumerate(entries) if sort_key(w)[0] == key]
        hits += [i for s, i in syns if sort_key(s)[0] == key and i not in hits]
        return [(entries[i][0], dz.read(entries[i][1], entries[i][2]).decode("utf-8")) for i in hits]

    return ifo, entries, syns, lookup
