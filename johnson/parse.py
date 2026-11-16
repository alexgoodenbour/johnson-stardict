"""Parse the LEME XML of Johnson's Dictionary into rendered entries.

The LEME markup (see https://leme.library.utoronto.ca/help/encoding) is:

    <wordentry>
      <form>HEADWORD. <class>n. s.</class></form>
      <xpln>
        <etym>[... <term lang="fr">foreign word</term> ...]</etym>
        1. Definition text.
        <term lang="quo">Illustrative quotation. Author.</term>
        2. ...
      </xpln>
    </wordentry>

Line breaks follow the printed page, with soft hyphens (&#173;) where a word
was broken across lines.  Sense numbers, quotation citations and verse layout
are not marked up, so they are recovered heuristically here.
"""

from __future__ import annotations

import html
import re
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

STRESS_MARK = "´"  # Johnson prints an acute accent after the stressed vowel
VOWELS = set("AEIOUYÆŒaeiouyæœ")


@dataclass
class Entry:
    keys: list[str]   # normalised lookup keys, primary first
    html: str         # rendered article for this <wordentry>


# --------------------------------------------------------------------------
# text helpers

def ws(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def esc(s: str) -> str:
    return html.escape(s, quote=False)


_C1_FIXES = str.maketrans({"\x95": "•", "\x88": "ˆ"})

# Runs of characters that were lost in transcription come through as '?'.
# In practice these are almost all Greek etymons (Greek letters that happen to
# look Latin, e.g. e/a/s/t/p, survive).  A token with several '?' is replaced
# by a marker; a single '?' inside an English word ("un?uly") is left alone.
_TOKEN = re.compile(r"[^\s\[\]();,:]+")


def _fix_lost(text: str) -> str:
    def repl(m):
        tok = m.group(0)
        core = tok.rstrip(".'\"")
        n = core.count("?")
        if n == 0 or re.fullmatch(r"[A-Za-z'’]+\?+", core):
            return tok  # no loss, or an ordinary question mark
        if n >= 2 or (len(core) >= 3 and n / len(core) >= 0.3):
            return "\x00LOST\x00" + tok[len(core):]
        return tok
    return _TOKEN.sub(repl, text)


def finish(text_html: str) -> str:
    """Final clean-up of an already-escaped HTML fragment."""
    text_html = text_html.translate(_C1_FIXES)
    parts = re.split(r"(<[^>]*>)", text_html)  # only touch text, never tags
    text_html = "".join(p if p.startswith("<") else _fix_lost(p) for p in parts)
    # collapse adjacent markers ("‹Greek› ‹Greek›" for one word split by damage)
    text_html = re.sub(r"\x00LOST\x00(?:\s*\x00LOST\x00)+", "\x00LOST\x00", text_html)
    return text_html.replace("\x00LOST\x00", '<span class="lost">‹Greek›</span>')


# --------------------------------------------------------------------------
# headwords

_ABBR = re.compile(r"^(?:[A-Z]\.\s?){2,}|^[A-Z]\.\s?[A-Z][a-z]+\.\s?")
_CONNECTORS = {"or", "and", "&", "more", "properly", "also", "possibly"}
# lowercase words that may sit inside a multi-word headword
# ("GOLD of Pleasure", "To HUSH up", "CAT in the pan", "SIX and seven")
_PARTICLES = {"of", "the", "a", "an", "in", "to", "by", "and", "up", "out", "at", "on",
              "with", "upon", "under", "de", "la", "le", "à", "me", "o"}
_END_PUNCT = re.compile(r"[.,;:!?\]]$")


def _is_caps(tok: str) -> bool:
    letters = [c for c in tok if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _bare(tok: str) -> str:
    return tok.strip(".,;:!?()[]")


def _apostrophes(s: str, stress: str) -> str:
    """Replace Johnson's stress marks, keeping real apostrophes.

    An apostrophe is kept for a possessive ("BEAR'S-EAR", "GOLDBEATER'S") or an
    elision after a single letter ("LOUIS D'OR"); otherwise it marks stress
    ("ABA'NDON", "AHA'").
    """
    out = []
    for i, c in enumerate(s):
        if c in "'’":
            prev = s[i - 1] if i else " "
            nxt = s[i + 1:i + 3]
            possessive = re.match(r"[sS](?![A-Za-z])", nxt) and prev.isalpha()
            elision = prev in "DLdl" and (i < 2 or not s[i - 2].isalpha()) and nxt[:1].isalpha()
            if not prev.isalpha():
                out.append("’")       # leading elision: 'GAN
            elif possessive or elision:
                out.append("'")
            else:
                out.append(stress)
        else:
            out.append(c)
    return "".join(out)


def normalise_key(phrase: str) -> str:
    k = _apostrophes(phrase, "").replace("’", "")
    k = k.strip(" .,;:!?()[]\"")
    k = re.sub(r"[()\[\]]", "", k)
    k = ws(k).lower().strip()
    return k


def ascii_fold(s: str) -> str:
    s = s.replace("æ", "ae").replace("œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def parse_form(text: str) -> tuple[str, list[str]]:
    """Split a printed headword line into (display html, lookup keys)."""
    s = ws(text).strip()
    s = re.sub(r"\.(?=[a-z])", ". ", s)                 # "LEAF.n. s." -> "LEAF. n. s."
    s = re.sub(r"(?<=[A-Z])\?(?=[A-Za-z])", "'", s)      # stress mark garbled to '?'
    s = s.lstrip(">")
    prefix = ""
    # "To ABA'NDON", "TO NOTCH", "A CHO'KER", "An ABRI'DGER", "The BETTER"
    m = re.match(r"(?:To|to|TO)\s+(?=\S)|(?:A|An|The)\s+(?=[A-Z][A-Z’'-]+\b)", s)
    if m:
        prefix, s = m.group(0), s[m.end():]

    m = _ABBR.match(s)
    if m:  # A. M., E. G., F. R. S. ...
        head = m.group(0).strip()
        keys = [head.replace(" ", "").lower()]
        tail = s[m.end():].strip()
        return _render_head(prefix + head, tail), keys

    tokens = s.split(" ")
    phrases: list[list[str]] = []

    def take_phrase(i: int, alternative: bool = False) -> int:
        start, cut = i, False
        while i < len(tokens):
            t, bare = tokens[i], _bare(tokens[i])
            if i > start and bare[:1].islower() and bare not in _PARTICLES:
                # a lowercase word may close the headword after a particle
                # ("MOTHER of pearl."), otherwise it starts the running text
                # ("HAN for have", "BILL n. s.", "WINTER is often used ...")
                if not (_END_PUNCT.search(t) and _bare(tokens[i - 1]) in _PARTICLES):
                    cut = True
                    break
            i += 1
            if _END_PUNCT.search(t) or i - start >= 6:
                break
        if cut and alternative:
            return -1  # "LILY of the Valley, or May lily." -- not a clean alternative
        if cut:  # don't end on a dangling particle: "WE'LCOME to our House"
            while i - start > 1 and _bare(tokens[i - 1]) in _PARTICLES:
                i -= 1
        phrases.append(tokens[start:i])
        return i

    i = take_phrase(0)
    while i < len(tokens):
        j, after_connector = i, False
        while j < len(tokens) and tokens[j].lower().strip(",") in _CONNECTORS:
            after_connector, j = True, j + 1
        if j >= len(tokens):
            break
        t = tokens[j].lstrip("(")
        if not (_is_caps(t) or (after_connector and t[:1].isupper())):
            break
        nxt = take_phrase(j, alternative=True)
        if nxt < 0:
            break
        i = nxt

    head = prefix + " ".join(tokens[:i])
    tail = " ".join(tokens[i:])
    keys = []
    for p in phrases:
        k = normalise_key(" ".join(p))
        if k and (len(k) > 2 or p is phrases[0]) and k not in keys:
            keys.append(k)
    return _render_head(head, tail), keys


def _render_head(head: str, tail: str) -> str:
    h = f"<b>{esc(_apostrophes(head, STRESS_MARK))}</b>"
    if tail:
        h += f" <i>{esc(tail)}</i>"
    return h


# --------------------------------------------------------------------------
# quotations

def _load_list(path: Path) -> set[str]:
    words = set()
    for line in path.read_text("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.update(line.split())
    return words


class Quotes:
    """Splits citations off quotations and detects verse."""

    _CANDIDATE = re.compile(
        r"(?:^|(?<=[.?!;:,'\"’)\]])\s+)(?P<w>(?:[1-4] )?(?P<name>[A-ZÆ][A-Za-z'’Æ]*))")

    def __init__(self, authors: set[str], prefixes: set[str]):
        self.authors = authors
        self.prefixes = prefixes  # "Sir", "Ben", "King" ... only before a name

    # what may follow an author's name in a citation: "Locke." "Locke, b. ii."
    # "Locke on Education." "Arbuthnot and Pope." "Job xiv. 21." "Locke" (end)
    _AFTER_NAME = re.compile(
        r"(?:[.,;:]|\s+(?:on|of|in|upon|to|and)\s|\s+[ivxlc]+[.,]|\s*$)")
    # a Bible reference needs no preceding punctuation: "... abide me Acts xx. 23."
    _BIBLE_REF = re.compile(r"\s(?P<w>(?:[1-4] )?(?P<name>[A-Z][a-z]+)\.? [ivxlc]+\. ?\d+\.?)$")

    def _is_citation_start(self, line: str, m: re.Match) -> bool:
        name = m.group("name")
        after = line[m.end("name"):]
        if name in self.prefixes and re.match(r"\.? [A-Z]", after):
            return True
        if name.endswith(("'s", "’s")):
            return name[:-2] in self.authors
        return name in self.authors and bool(self._AFTER_NAME.match(after))

    def split(self, lines: list[str]) -> tuple[list[str], str | None]:
        last = lines[-1]
        for m in self._CANDIDATE.finditer(last):
            start = m.start("w")
            if start == 0 and len(lines) == 1 and len(last) > 45:
                continue  # a long line is a quotation, not just a citation
            if len(last) - start > 90:
                continue
            if self._is_citation_start(last, m):
                body_last = last[:start].rstrip()
                return lines[:-1] + ([body_last] if body_last else []), last[start:]
        m = self._BIBLE_REF.search(last)
        if m and m.group("name") in self.authors:
            start = m.start("w")
            return lines[:-1] + [last[:start].rstrip()], last[start:]
        return lines, None

    @staticmethod
    def is_verse(lines: list[str]) -> bool:
        if len(lines) < 2:
            return False
        if statistics.median(len(l) for l in lines[:-1]) > 52:
            return False
        return all(l[:1].isupper() or l[:1] in "'‘\"(" or not l[:1].isalpha() for l in lines)

    def render(self, text: str) -> str:
        lines = [ws(l).strip() for l in text.split("\n")]
        lines = [esc(l) for l in lines if l]
        if not lines:
            return ""
        lines, cite = self.split(lines)
        if lines and self.is_verse(lines):
            # a lowercase line is a verse line that was too long for the column
            merged: list[str] = []
            for l in lines:
                if merged and l[:1].islower():
                    merged[-1] += " " + l
                else:
                    merged.append(l)
            body = "<br/>".join(merged)
            cls = "q v"
        else:
            body = " ".join(lines)
            cls = "q"
        out = f"<i>{body}</i>" if body else ""
        if cite:
            out += (" " if out else "") + f'<span class="au">{cite}</span>'
        return f'<div class="{cls}">{finish(out)}</div>'


# --------------------------------------------------------------------------
# definitions

_SENSE = re.compile(r"(?:^|(?<=\n)|(?<=[.;:?!\]] ))[ \t]*(\d{1,2})\.[ \t]+(?=[^\s\d])")


class _Body:
    def __init__(self, head_html: str):
        self.blocks: list[str] = []
        self.cur: list[str] = [head_html, " "]
        self.cur_cls = "d"
        self.sense = 0

    def add(self, s: str):
        self.cur.append(s)

    def flush(self):
        h = ws("".join(self.cur)).strip()
        if h:
            self.blocks.append(f'<p class="{self.cur_cls}">{finish(h)}</p>')
        self.cur = []

    def _ends_sentence(self) -> bool:
        text = re.sub(r"<[^>]+>", "", "".join(self.cur)).rstrip()
        return not text or text[-1] in ".;:?!]"

    def text(self, s: str, line_start: bool):
        """Add a run of definition text, starting a new paragraph at sense numbers.

        Only the next number in sequence counts as a sense number, which keeps
        stray numerals ("weighs 4. Some ...") in the running text.
        """
        pos = 0
        for m in _SENSE.finditer(s):
            n = int(m.group(1))
            if n != self.sense + 1:
                continue
            if m.start() == 0 and not (line_start or self._ends_sentence()):
                continue
            self.add(esc(s[pos:m.start()]))
            self.flush()
            self.cur_cls = "s"
            self.sense = n
            self.add(f"<b>{n}.</b> ")
            pos = m.end()
        self.add(esc(s[pos:]))

    def block(self, h: str):
        self.flush()
        self.cur_cls = "d"
        if h:
            self.blocks.append(h)


def _inline(el) -> str:
    """Render an element's content inline (etymologies, foreign words)."""
    parts = [esc(el.text or "")]
    for ch in el:
        if ch.tag == "term" and ch.get("lang") != "quo":
            parts.append(f"<i>{_inline(ch)}</i>")
        elif ch.tag == "damage":
            parts.append("?")
        elif ch.tag in ("pb", "lemenote"):
            pass
        else:
            parts.append(_inline(ch))
        parts.append(esc(ch.tail or ""))
    return "".join(parts)


def _plain(el) -> str:
    parts = [el.text or ""]
    for ch in el:
        if ch.tag == "damage":
            parts.append("?")
        elif ch.tag not in ("pb", "lemenote"):
            parts.append(_plain(ch))
        parts.append(ch.tail or "")
    return "".join(parts)


def render_entry(form_html: str, xpln, quotes: Quotes) -> str:
    body = _Body(form_html)
    line_start = True
    if xpln is not None:
        body.text(xpln.text or "", True)
        for ch in xpln:
            if ch.tag == "term" and ch.get("lang") == "quo":
                body.block(quotes.render(_plain(ch)))
                line_start = True
            elif ch.tag == "etym":
                body.add(f'<span class="et">{_inline(ch)}</span>')
                if (ch.tail or "")[:1].isalnum():
                    body.add(" ")  # "...French.]A writer" in the transcription
                line_start = True
            elif ch.tag == "term":
                body.add(f"<i>{_inline(ch)}</i>")
                line_start = False
            elif ch.tag == "class":
                body.add(f"<i>{_inline(ch)}</i>")
                line_start = False
            elif ch.tag == "damage":
                body.add("?")
                line_start = False
            # pb: page break, contributes nothing
            body.text(ch.tail or "", line_start)
            line_start = False
    body.flush()
    return "".join(body.blocks)


# --------------------------------------------------------------------------

def load_xml(path: Path):
    raw = path.read_text("utf-8")
    # rejoin words hyphenated across lines (possibly across a page break)
    raw = re.sub(r'&#173;(?:\s|<pb sig=""/>)*', "", raw)
    parser = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=True, huge_tree=True)
    return etree.fromstring(raw.encode("utf-8"), parser)


def parse(path: Path, data_dir: Path) -> list[Entry]:
    quotes = Quotes(_load_list(data_dir / "authors.txt"), _load_list(data_dir / "author-prefixes.txt"))
    root = load_xml(path)
    entries = []
    for we in root.iter("wordentry"):
        form = we.find("form")
        form_html, keys = parse_form(_plain(form))
        if not keys:
            continue
        entries.append(Entry(keys, render_entry(form_html, we.find("xpln"), quotes)))
    return entries
