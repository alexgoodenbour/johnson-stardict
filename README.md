# Johnson's Dictionary (1755) for KOReader

A StarDict edition of Samuel Johnson's *A Dictionary of the English Language*
(first folio edition, London, 1755), made for [KOReader](https://koreader.rocks).
Long-press a word in any book and see what Johnson said about it.

> **LEXICO´GRAPHER.** *n. s.* A writer of dictionaries; a harmless drudge, that
> busies himself in tracing the original, and detailing the signification of
> words.

It is a standard StarDict dictionary, so it also works in GoldenDict, sdcv and
other StarDict readers.

## Source

The text comes from the transcription in
[*Lexicons of Early Modern English*](https://leme.library.utoronto.ca) (LEME),
edited by Ian Lancashire at the University of Toronto. It is LEME lexicon 1345,
and its XML is deposited in TSpace at <https://hdl.handle.net/1807/124274>. LEME
publishes it under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The build script downloads that XML and converts it. Nothing is hand-edited.

## What's in it

- All 42,726 entries of the 1755 text, merged into 37,106 headwords.
- Johnson's illustrative quotations in italics, with the author's name in
  roman as in the printed book. Verse quotations keep their line breaks.
- Numbered senses on their own lines, etymologies, and Johnson's stress marks
  (ABA´NDON).
- Lookup by the word as it appears in a modern book. Inflected forms
  (*abandoned*, *mice*) and US spellings (*color*) open Johnson's entry
  (ABANDON, MOUSE, COLOUR). Johnson's own spellings stay as headwords
  (*musick*, *publick*).

## Installing in KOReader

1. Download `johnson1755-stardict.zip` from the
   [latest release](../../releases/latest).
2. Unzip it. You get a folder called `johnson1755`.
3. Connect your e-reader by USB and copy the `johnson1755` folder into
   KOReader's `data/dict/` folder:

   | Device     | Copy into                                        |
   | ---------- | ------------------------------------------------ |
   | Kobo       | `.adds/koreader/data/dict/`                      |
   | Kindle     | `koreader/data/dict/`                            |
   | PocketBook | `applications/koreader/data/dict/`               |
   | Android    | `koreader/data/dict/` (on internal storage)      |

   On Kobo, `.adds` is a hidden folder. Turn on hidden files in your file
   manager if you can't see it. When you're done you should have
   `…/data/dict/johnson1755/johnson1755.ifo`.
4. Eject the device and restart KOReader. It only looks for new dictionaries
   when it starts.
5. Open a book and long-press a word.

If you have more than one dictionary installed, KOReader shows each one's
result in turn. To put Johnson first, or to turn it off, go to the
**Search** menu (magnifying glass) → **Settings** → **Dictionary settings** →
**Manage dictionaries**.

Keep `johnson1755.css` in the folder. KOReader uses it to lay out the entries.
Other readers ignore it.

## Building it yourself

You need Python 3.10 or newer and lxml.

```sh
pip install -r requirements.txt
python3 build.py
```

This downloads the two sources into `sources/` and checks their SHA-256
hashes. It then writes `dist/johnson1755/` and `dist/johnson1755-stardict.zip`.
Finally it reads the dictionary back to check its structure and test some
sample lookups. A build takes under a minute.

| File                          | Purpose                                                        |
| ----------------------------- | -------------------------------------------------------------- |
| `build.py`                    | Entry point: download, parse, write, check, zip                |
| `johnson/sources.py`          | Source URLs and their pinned checksums                         |
| `johnson/parse.py`            | LEME XML to HTML entries: headwords, senses, quotations, verse |
| `johnson/modern.py`           | Inflected and US forms from the English Speller Database       |
| `johnson/stardict.py`         | StarDict and dictzip writer and reader                         |
| `data/authors.txt`            | Names that begin a quotation's citation (set in roman)         |
| `data/author-prefixes.txt`    | Words like *Sir* that begin a citation only before a name      |
| `data/johnson.css`            | Stylesheet, shipped as `johnson1755.css`                       |
| `data/LICENSE-dictionary.txt` | Licence for the built dictionary, shipped as `LICENSE.txt`     |

## Licensing

**Dictionary.** Johnson's text is in the public domain. The LEME
transcription is CC BY 4.0, so the StarDict edition built from it is also
CC BY 4.0, with attribution to LEME as above. The changes made to the source
are listed in [`data/LICENSE-dictionary.txt`](data/LICENSE-dictionary.txt),
which ships in the zip as `LICENSE.txt`.

**Lookup forms.** The extra lookup keys in the `.syn` file come from the
[English Speller Database](https://github.com/en-wl/wordlist) (formerly
SCOWL), Copyright 2000-2026 Kevin Atkinson. Its MIT-like licence requires its
notice to accompany copies, so the notice is included in full in
`LICENSE.txt`.

**Code.** The build scripts in this repository are MIT-licensed. See
[`LICENSE`](LICENSE).

## Known limitations

- **Greek.** Many Greek etymons were lost before the transcription reached
  LEME, where they appear as `?e????`. They are shown as ‹Greek›. Greek that
  survived is shown normally.
- **Recovered structure.** The source marks up headword, part of speech,
  etymology and quotations. It does not mark sense numbers, verse lines or
  citations, so these are recovered heuristically. About 98.6% of quotations
  get their citation set apart. Where a heuristic misses, the text is all
  still there, just less nicely formatted.
- **Transcription errors.** The text follows the source, which has
  occasional typos and tagging slips. A few definitions are tagged as
  quotations.
- **Edition.** This is the 1755 first edition, not Johnson's revised fourth
  edition of 1773.
