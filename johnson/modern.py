"""Map inflected forms onto Johnson's headwords.

Johnson's headwords are lemmas ("To ABA'NDON", "MOUSE").  E-readers look up
the exact word tapped in the text ("abandoned", "mice"), so the dictionary gets
extra lookup keys (StarDict synonyms):

1. every inflected form that the English Speller Database (ESDB, formerly
   SCOWL) lists for the same lemma (abandon -> abandoned, abandoning, abandons;
   mouse -> mice).  ESDB groups US/UK variants with the lemma, so these come
   along too (colour -> color, colors);
2. ASCII spellings of headwords with ligatures or accents (æ -> ae).

Johnson's own archaic spellings (musick, publick) are deliberately left alone.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .parse import ascii_fold

INFLECTION_MAX_SIZE = 80   # ESDB size: 80 = "a valid word in current usage"

_SKIP_POS = {"abbr", "x", "pre", "suf", "wp", "we", "s"}
_VAR_TOKEN = r"[ABZCD_][.=?v~V\-@x]?(?: \{\d+\})?"
_LINE = re.compile(
    r"^(?P<info>[^:]*?): "
    rf"(?:(?P<var>\+|{_VAR_TOKEN}(?: {_VAR_TOKEN})*): )?"
    r"(?P<lemma>[^<{(:]+?)(?: <(?P<pos>[^>]*)>)?(?: \{[^}]*\})?(?: \([^)]*\))?"
    r"(?:: (?P<forms>.*))?$"
)


def _split_top(s: str) -> list[str]:
    """Split on ', ' outside parentheses."""
    out, depth, cur = [], 0, []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if depth == 0 and s.startswith(", ", i):
            out.append("".join(cur))
            cur = []
            i += 2
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _clean(word: str) -> str | None:
    word = word.strip()
    if ": " in word:  # "~: abaci" (variant info before a derived form)
        var, word = word.rsplit(": ", 1)
        if "x" in var:
            return None
    word = word.rstrip("*-@~!†").lstrip("-@!")
    if not word or word == "-" or "'" in word or any(c.isupper() for c in word):
        return None
    return word


class ESDB:
    def __init__(self, path: Path):
        self.groups: list[set[str]] = []
        self.by_lemma: dict[str, set[int]] = defaultdict(set)
        group: set[str] = set()
        lemmas: set[str] = set()

        def close():
            nonlocal group, lemmas
            if group:
                gid = len(self.groups)
                self.groups.append(group)
                for l in lemmas:
                    self.by_lemma[l].add(gid)
            group, lemmas = set(), set()

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = re.split(r"\s#", line.rstrip("\n"), maxsplit=1)[0].rstrip()
                if not line:
                    close()
                    continue
                m = _LINE.match(line)
                if not m:
                    continue
                info = m.group("info")
                sizes = [int(x) for x in re.findall(r"\b\d+\b", info)]
                if not sizes or min(sizes) > INFLECTION_MAX_SIZE or "AU" in info.split():
                    continue
                var = m.group("var") or ""
                if var and var != "+":
                    toks = var.split()
                    spell = {t[0] for t in toks if not t.startswith("{")}
                    levels = {t[1:2] for t in toks if not t.startswith("{")}
                    if spell <= {"D"} or levels == {"x"}:
                        continue
                pos = (m.group("pos") or "").split("/")[0]
                if pos in _SKIP_POS:
                    continue
                words = []
                lemma = _clean(m.group("lemma"))
                if lemma:
                    words.append(lemma)
                    lemmas.add(lemma)
                for item in _split_top(m.group("forms") or ""):
                    item = item.strip()
                    if item.startswith("(") and item.endswith(")"):
                        words += [w for w in map(_clean, item[1:-1].split(" | ")) if w]
                    elif (w := _clean(item)):
                        words.append(w)
                group.update(words)
        close()

    def forms(self, lemma: str) -> set[str]:
        out: set[str] = set()
        for gid in self.by_lemma.get(lemma, ()):
            out |= self.groups[gid]
        return out


def build_synonyms(johnson_keys: set[str], esdb: ESDB) -> dict[str, set[str]]:
    """Return {synonym: {johnson key, ...}}."""
    syn: dict[str, set[str]] = defaultdict(set)
    for k in johnson_keys:
        bases = {k, ascii_fold(k)}
        for b in bases:
            syn[b].add(k)
            for f in esdb.forms(b):
                syn[f].add(k)
    for s in list(syn):
        syn[s].discard(s)  # a word is never a synonym of itself
        if not syn[s]:
            del syn[s]
    return dict(syn)
