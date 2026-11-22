"""Build the paper in the format of Proceedings on Engineering Sciences (PES).

uv run --with python-docx==1.2.0 python paper/pes/build_pes.py
uv run --with python-docx==1.2.0 python paper/pes/build_pes.py --pdf
uv run --with python-docx==1.2.0 python paper/pes/build_pes.py --overlap a.txt b.txt

The text is read from paper/main.tex and paper/sections/*.tex and every number from
paper/generated/numbers.tex, so this version cannot drift from the LaTeX paper. The journal's
look comes from its own Word template (header, logos, styles, running head, licence and QR
code); the template's sample paper is removed and only its layout is kept. Citations are taken
from paper/references.bib and set author-year, as the journal does.
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.text.paragraph import Paragraph

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
ROOT = PAPER.parent
NUMBERS = PAPER / "generated" / "numbers.tex"
BIB = PAPER / "references.bib"
SECTIONS = [
    "introduction",
    "related",
    "dataset",
    "methods",
    "results",
    "discussion",
    "conclusion",
]
OUT_DOCX = HERE / "sixth-finger-bci-pes.docx"
OUT_PDF = HERE / "sixth-finger-bci-pes.pdf"
DEFAULT_TEMPLATE = Path.home() / "Downloads" / "PES 2026.docx"
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
FONT_DIR = Path("/System/Library/Fonts/Supplemental")

CORRESPONDING = "Suman Lata"
EMAILS = {
    "Rajveer Singh": "rajveer_ece_27@msit.in",
    "Ansh Dahiya": "ansh_ece_27@msit.in",
    "Suman Lata": "suman@msit.in",
}
EMAIL_PLACEHOLDER = "e-mail to be added"
RUNNING_AUTHOR = "Singh"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = f'xmlns:w="{W_NS}" xmlns:m="{M_NS}"'

# Column and page widths of the template (A4, 2 cm margins, 1 cm gutter), in EMU.
COLUMN_EMU = 2844000
PAGE_EMU = 6084000
PAGE_TWIPS = 9639

WEB = ROOT / "docs" / "figures" / "web"
FIGS = ROOT / "docs" / "figures"


@dataclass
class Figure:
    path: Path
    wide: bool
    caption: str


# One job per figure. Captions may use LaTeX and the macros of numbers.tex.
FIGURES: dict[str, Figure] = {
    "system": Figure(
        WEB / "system.png",
        True,
        "The parts of a sixth-finger motor-imagery BCI: (1) EEG cap, (2) amplifier, (3) the "
        "4\\,s window the decoder reads, (4) the decoder and (5) the robotic finger. This study "
        "calibrates part 4, offline; no decoder drove the finger.",
    ),
    "trial": Figure(
        WEB / "trial.png",
        False,
        "One trial as the patient saw it: rest under a fixation cross, a grey circle to get "
        "ready, and a picture cueing imagined hand or sixth-finger movement, with the "
        "article's nominal timings. One 4\\,s window is read from the rest and one from the "
        "imagery period.",
    ),
    "session": Figure(
        WEB / "session.png",
        True,
        "Every decoder learned from runs 1--2 of a session and was tested on runs 3--4, which "
        "no step saw. Each patient was recorded before therapy, after it and a month later.",
    ),
    "protocol": Figure(
        WEB / "leak.png",
        False,
        "Where the leak enters, drawn for 20 trials. In the dataset's script (``the paper's "
        "way'') the spatial filters are fitted on every trial, test trials included, before "
        "cross-validation; leakage-free, only on the training trials. The accuracies are those "
        "of Section~\\ref{sec:leak}.",
    ),
    "leak": Figure(
        FIGS / "paper_leak.png",
        False,
        "Hand against sixth finger with CSP+LDA, patient by patient (pre-therapy session, "
        "$n = \\rqOneN$): every patient scores lower once the filters are fitted inside the "
        "training folds. Grey: patients; black: mean and 95\\,\\% CI; dashed: chance.",
    ),
    "setup": Figure(
        WEB / "setup.png",
        False,
        "Calibration for a new patient (three classes, pre-therapy session, "
        "$n = \\rqTwoHTwoAN$), against nominal minutes of labelled recording ($k = 1$, 2, 3, "
        "5, 10 and all trials of each movement). Solid: re-centred transfer (RCT-TS+LR); "
        "dashed: from scratch (TS+LR); bands: 95\\,\\% CIs. Transfer starts high and stays "
        "nearly flat.",
    ),
    "rqthree": Figure(
        FIGS / "rq3_patients.png",
        False,
        "The new command, patient by patient (pre-therapy session, $n = \\rqThreeHThreeAN$). "
        "Left: transfer minus from scratch, ALC over $k = 1, 2, 3, 5$ (H3a, H3b). Right: "
        "transfer minus the own-hand decoder, finger against rest (H3c). Above zero favours "
        "transfer. Grey: patients; black: mean and 95\\,\\% CI.",
    ),
    "later": Figure(
        WEB / "later.png",
        False,
        "The first session's TS+LR decoder, unchanged, on later days (exploratory; three "
        "classes, runs 3--4). Grey bar: within the first session; black: two weeks and a "
        "month later; dashed: chance.",
    ),
    "switch": Figure(
        WEB / "switch-patients.png",
        False,
        "The sixth finger as a switch (post hoc, runs 3--4, $n = \\rqFourCueN$), one dot per "
        "patient. Sixth finger against rest (TS+LR, 14 central channels) separates well; hand "
        "against sixth finger (pre-trained, fine-tuned EEGNet, the best of the decoders "
        "tried) far less. Line: mean; dashed: chance.",
    ),
    "path": Figure(
        WEB / "path.png",
        True,
        "Where this study sits on a patient's path. Parts drawn solid were built in this "
        "project (the decoder, its server and the demonstrator); dashed parts are needed for "
        "a closed-loop system and were not built.",
    ),
}

# The LaTeX paper's figure labels, mapped to the figure that stands for each here.
LABEL_FIGURE = {
    "fig:leak": "leak",
    "fig:setup": "setup",
    "fig:rqthree": "rqthree",
    "fig:later": "later",
    "fig:switch": "switch",
}

# Additions to the LaTeX text: the figures it does not have, the equations the methods use,
# and one reference list narrowed to the figures that still show single patients. Each anchor
# must be found exactly once, so a change to the paper stops the build instead of being lost.
EDITS: list[tuple[str, str]] = [
    (
        "learns to recognise this change in the electroencephalogram (EEG).",
        "learns to recognise this change in the electroencephalogram (EEG) (\\PESref{system}).",
    ),
    ("\\section{Related Work}", "\\PESfig{system}\n\n\\section{Related Work}"),
    (
        "flexing a robotic sixth finger worn on the affected wrist.",
        "flexing a robotic sixth finger worn on the affected wrist (\\PESref{trial}).",
    ),
    (
        "Before any analysis we audited every file.",
        "\\PESfig{trial}\n\nBefore any analysis we audited every file.",
    ),
    (
        "of the same session, which no step ever saw.",
        "of the same session, which no step ever saw (\\PESref{session}).",
    ),
    (
        "\\subsection{Decoders}",
        "\\PESfig{session}\n\n\\subsection{Decoders}",
    ),
    (
        "so that all patients share one reference point~\\cite{zanini2018}.",
        "so that all patients share one reference point~\\cite{zanini2018}. For a patient "
        "whose covariance matrices have the Riemannian mean $M$, each matrix $C_i$ becomes\n"
        "\\PESeq{recentre}\nwhich moves that patient's mean to the identity matrix.",
    ),
    (
        "leave one run out and runs 1--2 against 3--4 (chronological).",
        "leave one run out and runs 1--2 against 3--4 (chronological). "
        "\\PESref{protocol} shows what the first step learns from in each of the first two."
        "\n\n\\PESfig{protocol}\n\n",
    ),
    (
        "The metric is balanced accuracy, with the patient as the unit; differences in "
        "accuracy are in percentage points.",
        "The metric is balanced accuracy, with the patient as the unit; differences in "
        "accuracy are in percentage points. Balanced accuracy is the mean recall over the "
        "$K$ classes of a task,\n\\PESeq{ba}\nwhere $n_c$ is the number of test windows of "
        "class $c$ and $t_c$ the number of them decoded as $c$.",
    ),
    (
        "Figs.~\\ref{fig:leak}, \\ref{fig:rqthree}, \\ref{fig:later} and~\\ref{fig:switch}",
        "Figs.~\\ref{fig:leak}, \\ref{fig:rqthree} and~\\ref{fig:switch}",
    ),
    (
        "A closed-loop study in which the decoder drives the finger is the next test.",
        "A closed-loop study in which the decoder drives the finger is the next test "
        "(\\PESref{path}).\n\n\\PESfig{path}\n\n",
    ),
]

SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to"}


class BuildError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- numbers


def load_macros() -> dict[str, str]:
    """The macros of numbers.tex, name to LaTeX value."""
    macros: dict[str, str] = {}
    for line in NUMBERS.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", line.strip())
        if m:
            macros[m.group(1)] = m.group(2)
    if not macros:
        raise BuildError(f"no macros in {NUMBERS}")
    return macros


# ----------------------------------------------------------------------------- references


ACCENTS = {"'": "\u0301", '"': "\u0308", "`": "\u0300", "^": "\u0302", "~": "\u0303"}


def bib_text(s: str) -> str:
    """BibTeX field to plain text: accents, braces, dashes and quotes."""
    s = re.sub(
        r"\{?\\(['\"`^~])\{?([A-Za-z])\}?\}?",
        lambda m: unicodedata.normalize("NFC", m.group(2) + ACCENTS[m.group(1)]),
        s,
    )
    s = s.replace("``", '"').replace("''", '"').replace("---", "—").replace("--", "–")
    s = s.replace("\\&", "&").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_bib() -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    text = BIB.read_text(encoding="utf-8")
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        start, depth, i = m.end(), 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start : i - 1]
        fields = {"type": m.group(1).lower()}
        for f in re.finditer(r"(\w+)\s*=\s*\{", body):
            j, d = f.end(), 1
            while d:
                d += {"{": 1, "}": -1}.get(body[j], 0)
                j += 1
            fields[f.group(1).lower()] = body[f.end() : j - 1]
        entries[m.group(2)] = fields
    return entries


def split_authors(raw: str) -> list[tuple[str, str]]:
    """(surname, given names) pairs; 'others' becomes ('', 'others')."""
    people = []
    for name in re.split(r"\s+and\s+", raw.strip()):
        name = bib_text(name)
        if name == "others":
            people.append(("", "others"))
        elif "," in name:
            last, first = (p.strip() for p in name.split(",", 1))
            people.append((last, first))
        else:
            *first, last = name.split()
            people.append((last, " ".join(first)))
    return people


def initials(given: str) -> str:
    out = []
    for token in re.split(r"[\s.]+", given):
        if not token:
            continue
        parts = [p for p in token.split("-") if p]
        out.append("-".join((p[0].upper() if n else p[0]) + "." for n, p in enumerate(parts)))
    return " ".join(out)


def cite_label(entry: dict[str, str]) -> str:
    people = split_authors(entry["author"])
    names = [last for last, _ in people if last]
    if len(people) == 1:
        return names[0]
    if len(people) == 2 and len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} et al."


def author_key(entry: dict[str, str]) -> list[tuple[str, str]]:
    """Sort key of the reference list: surnames, then initials, author by author."""
    return [
        (unicodedata.normalize("NFKD", last).lower(), initials(given).lower())
        for last, given in split_authors(entry["author"])
    ]


class Bibliography:
    def __init__(self, keys: list[str]) -> None:
        bib = parse_bib()
        missing = [k for k in keys if k not in bib]
        if missing:
            raise BuildError(f"citations not in references.bib: {missing}")
        self.entries = {k: bib[k] for k in keys}
        groups: dict[tuple[str, str], list[str]] = {}
        for k, e in self.entries.items():
            groups.setdefault((cite_label(e), e["year"]), []).append(k)
        self.suffix = {k: "" for k in keys}
        for same in groups.values():
            if len(same) > 1:
                ordered = sorted(
                    same,
                    key=lambda k: (author_key(self.entries[k]), bib_text(self.entries[k]["title"])),
                )
                for letter, k in zip("abcdefgh", ordered, strict=False):
                    self.suffix[k] = letter

    def year(self, key: str) -> str:
        return self.entries[key]["year"] + self.suffix[key]

    def label(self, key: str) -> str:
        return cite_label(self.entries[key])

    def parenthetical(self, keys: list[str]) -> str:
        return "(" + "; ".join(f"{self.label(k)}, {self.year(k)}" for k in keys) + ")"

    def narrative(self, name: str, keys: list[str]) -> str:
        own = [k for k in keys if self.label(k) == name]
        rest = [k for k in keys if self.label(k) != name]
        parts = [", ".join(self.year(k) for k in own)]
        parts += [f"{self.label(k)}, {self.year(k)}" for k in rest]
        return f"{name} (" + "; ".join(parts) + ")"

    def authors_apa(self, raw: str) -> str:
        people = split_authors(raw)
        others = any(given == "others" for _, given in people)
        names = [f"{last}, {initials(given)}" for last, given in people if last]
        if others:
            return ", ".join(names) + ", et al."
        if len(names) == 1:
            return names[0]
        if len(names) > 20:
            return ", ".join(names[:19]) + ", ... " + names[-1]
        return ", ".join(names[:-1]) + ", & " + names[-1]

    def reference(self, key: str) -> list[tuple[str, bool]]:
        """One APA-style entry as (text, italic) pieces, in the template's layout."""
        e = self.entries[key]
        head = f"{self.authors_apa(e['author'])} ({self.year(key)}). "
        title = bib_text(e["title"]).rstrip(".")
        pages = bib_text(e.get("pages", ""))
        kind = e["type"]
        if kind == "article":
            tail = ""
            if "volume" in e:
                tail += f", {e['volume']}"
                if "number" in e:
                    tail += f"({e['number']})"
            if pages:
                tail += f", {pages}" if "–" in pages else f", Article {pages}"
            if "volume" not in e and not pages:
                tail = ". Advance online publication"
            return [
                (head + title + ". ", False),
                (bib_text(e["journal"]), True),
                (tail + ".", False),
            ]
        if kind == "inproceedings":
            tail = f" (pp. {pages})." if pages else "."
            return [
                (head + title + ". In ", False),
                (bib_text(e["booktitle"]), True),
                (tail, False),
            ]
        version = re.search(r"[Vv]ersion ([\w.]+)", e.get("note", ""))
        what = "Data set" if "dataset" in e.get("howpublished", "") else "Computer software"
        tail = f" (Version {version.group(1)}) [{what}]." if version else f" [{what}]."
        publisher = bib_text(e.get("publisher", ""))
        if not publisher and "Zenodo" in e.get("howpublished", ""):
            publisher = "Zenodo"
        if publisher:
            tail += f" {publisher}."
        return [(head, False), (title, True), (tail, False)]

    def order(self) -> list[str]:
        return sorted(self.entries, key=lambda k: (author_key(self.entries[k]), self.year(k)))


# ----------------------------------------------------------------------------- LaTeX text


@dataclass(frozen=True)
class Run:
    text: str
    italic: bool = False
    bold: bool = False
    vert: str = ""  # "superscript" or "subscript"
    red: bool = False


SYMBOLS = {
    "leq": "≤",
    "geq": "≥",
    "in": "∈",
    "times": "×",
    "dagger": "†",
    "infty": "∞",
    "ldots": "…",
    "pm": "±",
    "approx": "≈",
}
UPRIGHT = {"ln", "min", "max", "exp", "log"}
SILENT = {"par", "raggedright", "noindent", "centering", "footnotesize", "small"}


class Latex:
    """Converts the paper's LaTeX subset to runs; anything unknown stops the build."""

    def __init__(self, macros: dict[str, str]) -> None:
        self.macros = macros

    def group(self, s: str, i: int) -> tuple[str, int]:
        if i >= len(s) or s[i] != "{":
            raise BuildError(f"expected a group at: {s[i : i + 40]!r}")
        depth, j = 1, i + 1
        while depth:
            if j >= len(s):
                raise BuildError(f"unbalanced braces in: {s[i : i + 60]!r}")
            if s[j] == "\\":
                j += 2
                continue
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        return s[i + 1 : j - 1], j

    def runs(
        self, s: str, italic: bool = False, bold: bool = False, math: bool = False
    ) -> list[Run]:
        out: list[Run] = []

        def add(text: str, it: bool = italic, vert: str = "") -> None:
            out.append(Run(text, it, bold, vert))

        i = 0
        while i < len(s):
            c = s[i]
            if c == "\\":
                m = re.match(r"\\([A-Za-z]+)", s[i:])
                if not m:
                    nxt = s[i + 1]
                    i += 2
                    if nxt == ",":
                        if not s.startswith("\\%", i):
                            add("\u00a0")
                    elif nxt in "%_&{}#$":
                        add(nxt)
                    elif nxt in " \\":
                        add(" ")
                    else:
                        raise BuildError(f"unknown control symbol \\{nxt}")
                    continue
                name = m.group(1)
                i += len(m.group(0))
                if name in self.macros:
                    if s.startswith("{}", i):
                        i += 2
                    value = self.macros[name]
                    if "TBD" in value:
                        raise BuildError(f"macro {name} is still TBD")
                    out += self.runs(value, italic, bold, math)
                elif name == "ensuremath":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, italic, bold, True)
                elif name in ("emph", "textit"):
                    arg, i = self.group(s, i)
                    out += self.runs(arg, not italic, bold, math)
                elif name == "textbf":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, italic, True, math)
                elif name in ("texttt", "text", "mathrm", "textrm"):
                    arg, i = self.group(s, i)
                    out += self.runs(arg, italic and not math, bold, False)
                elif name == "hat":
                    arg, i = self.group(s, i)
                    add(arg + "\u0302", True)
                elif name in SYMBOLS:
                    add(SYMBOLS[name])
                elif name in UPRIGHT:
                    add(name, italic and not math)
                elif name in SILENT:
                    pass
                elif name in ("label",):
                    _, i = self.group(s, i)
                elif re.fullmatch(r"[a-z]+[A-Z]\w*", name):
                    raise BuildError(f"macro \\{name} is not in numbers.tex")
                else:
                    raise BuildError(f"unknown command \\{name}")
                continue
            if c == "{":
                arg, i = self.group(s, i)
                out += self.runs(arg, italic, bold, math)
                continue
            if c == "$":
                j = s.index("$", i + 1)
                out += self.runs(s[i + 1 : j], italic, bold, True)
                i = j + 1
                continue
            if c == "~":
                add("\u00a0")
                i += 1
                continue
            if math and c in "^_":
                vert = "superscript" if c == "^" else "subscript"
                i += 1
                if s[i] == "{":
                    arg, i = self.group(s, i)
                elif s[i] == "\\":
                    m = re.match(r"\\([A-Za-z]+)", s[i:])
                    arg, i = s[i : i + len(m.group(0))], i + len(m.group(0))
                else:
                    arg, i = s[i], i + 1
                for r in self.runs(arg, italic, bold, True):
                    out.append(Run(r.text, r.italic, r.bold, vert))
                continue
            if s.startswith("---", i):
                add("—")
                i += 3
                continue
            if s.startswith("--", i):
                add("–")
                i += 2
                continue
            if s.startswith("``", i) or s.startswith("''", i):
                add('"')
                i += 2
                continue
            if math:
                if c == "-":
                    add("−")
                elif c.isalpha():
                    add(c, True)
                elif c.isspace():
                    add(" ")
                else:
                    add(c)
                i += 1
                continue
            j = i
            while j < len(s) and s[j] not in "\\{$~^_-`'":
                j += 1
            if j == i:
                j = i + 1
            if "}" in s[i:j]:
                raise BuildError(f"stray brace in: {s[i : i + 60]!r}")
            add(s[i:j])
            i = j
        return merge(out)

    def plain(self, s: str) -> str:
        return "".join(r.text for r in self.runs(s))


def merge(runs: list[Run]) -> list[Run]:
    out: list[Run] = []
    for r in runs:
        text = re.sub(r"[ \t\n]+", " ", r.text)
        if out and (out[-1].italic, out[-1].bold, out[-1].vert, out[-1].red) == (
            r.italic,
            r.bold,
            r.vert,
            r.red,
        ):
            out[-1] = Run(out[-1].text + text, r.italic, r.bold, r.vert, r.red)
        else:
            out.append(Run(text, r.italic, r.bold, r.vert, r.red))
    joined: list[Run] = []
    for r in out:
        if joined and joined[-1].text.endswith(" ") and r.text.startswith(" "):
            r = Run(r.text[1:], r.italic, r.bold, r.vert, r.red)
        if r.text:
            joined.append(r)
    return joined


def strip_comments(tex: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in tex.splitlines())


def normalise(tex: str) -> str:
    """Single newlines to spaces, blank lines kept as paragraph breaks."""
    paras = re.split(r"\n\s*\n", strip_comments(tex))
    return "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paras if p.strip())


def environment(tex: str, name: str) -> list[re.Match]:
    return list(
        re.finditer(rf"\\begin\{{{re.escape(name)}\}}(.*?)\\end\{{{re.escape(name)}\}}", tex, re.S)
    )


# ----------------------------------------------------------------------------- document parts


def title_case(text: str) -> str:
    def word(w: str, first: bool) -> str:
        if w.lower() in SMALL_WORDS and not first:
            return w.lower()
        return "-".join(p[:1].upper() + p[1:] for p in w.split("-"))

    head, paren, rest = text.partition("(")
    words = head.split(" ")
    head = " ".join(word(w, n == 0) if w else w for n, w in enumerate(words))
    return head + paren + rest


# Symbols Times New Roman lacks; set in the template's equation font instead.
MATH_ONLY = "∈"


def run_xml(r: Run, size: int = 20, explicit: bool = False) -> str:
    """One run; explicit switches bold and italic off where the style turns them on."""
    props = ""
    if r.bold:
        props += "<w:b/>"
    elif explicit:
        props += '<w:b w:val="0"/>'
    if r.italic:
        props += "<w:i/>"
    elif explicit:
        props += '<w:i w:val="0"/>'
    if r.red:
        props += '<w:color w:val="FF0000"/>'
    props += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    if r.vert:
        props += f'<w:vertAlign w:val="{r.vert}"/>'
    out = ""
    for piece in re.split(f"([{MATH_ONLY}])", r.text):
        if not piece:
            continue
        font = (
            '<w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
            if piece in MATH_ONLY
            else ""
        )
        text = piece.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        out += f'<w:r><w:rPr>{font}{props}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r>'
    return out


def para_xml(
    style: str, runs: list[Run], ppr_extra: str = "", size: int = 20, explicit: bool = False
) -> str:
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    runs = list(runs)
    if runs:
        first, last = runs[0], runs[-1]
        runs[0] = Run(first.text.lstrip(), first.italic, first.bold, first.vert, first.red)
        last = runs[-1]
        runs[-1] = Run(last.text.rstrip(), last.italic, last.bold, last.vert, last.red)
    body = "".join(run_xml(r, size, explicit) for r in runs if r.text)
    return (
        f"<w:p {NS}><w:pPr>{style_xml}{ppr_extra}"
        f'<w:rPr><w:sz w:val="{size}"/></w:rPr></w:pPr>{body}</w:p>'
    )


TEXT_PPR = '<w:ind w:firstLine="0"/>'
LIST_PPR = '<w:tabs><w:tab w:val="left" w:pos="284"/></w:tabs><w:ind w:left="284" w:hanging="284"/>'
REFERENCE_PPR = (
    '<w:tabs><w:tab w:val="left" w:pos="5103"/></w:tabs><w:ind w:left="187" w:hanging="187"/>'
)


# OMML, the equations of the methods.
def m_run(text: str, upright: bool = False) -> str:
    sty = '<m:rPr><m:sty m:val="p"/></m:rPr>' if upright else ""
    return (
        f'<m:r>{sty}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
        f'<w:sz w:val="20"/></w:rPr><m:t xml:space="preserve">{text}</m:t></m:r>'
    )


def m_sub(base: str, sub: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def m_sup(base: str, sup: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"


def m_frac(num: str, den: str) -> str:
    return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"


def m_nary(chr_: str, low: str, high: str, body: str) -> str:
    return (
        f'<m:nary><m:naryPr><m:chr m:val="{chr_}"/><m:limLoc m:val="undOvr"/></m:naryPr>'
        f"<m:sub>{low}</m:sub><m:sup>{high}</m:sup><m:e>{body}</m:e></m:nary>"
    )


def equations() -> dict[str, str]:
    x_min = m_sub(m_run("x"), m_run("min", True))
    x_max = m_sub(m_run("x"), m_run("max", True))
    alc = (
        m_run("ALC", True)
        + m_run("=")
        + m_frac(m_run("1", True), x_max + m_run("−") + x_min)
        + m_nary(
            "∫",
            x_min,
            x_max,
            m_frac(
                m_run("BA", True) + m_run("(x)") + m_run("−") + m_run("c"),
                m_run("1", True) + m_run("−") + m_run("c"),
            )
            + m_run("d", True)
            + m_run("x"),
        )
    )
    ba = (
        m_run("BA", True)
        + m_run("=")
        + m_frac(m_run("1", True), m_run("K"))
        + m_nary(
            "∑",
            m_run("c") + m_run("=1", True),
            m_run("K"),
            m_frac(m_sub(m_run("t"), m_run("c")), m_sub(m_run("n"), m_run("c"))),
        )
    )
    half = m_run("−1/2", True)
    recentre = (
        m_sub(m_run("C\u0303"), m_run("i"))
        + m_run("=")
        + m_sup(m_run("M"), half)
        + m_sub(m_run("C"), m_run("i"))
        + m_sup(m_run("M"), half)
    )
    return {"recentre": recentre, "ba": ba, "alc": alc}


def equation_xml(omml: str, number: int) -> str:
    tab = '<w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:tab/></w:r>'
    return (
        f'<w:p {NS}><w:pPr><w:pStyle w:val="Jednacina"/><w:rPr><w:sz w:val="20"/></w:rPr>'
        f"</w:pPr>{tab}<m:oMath>{omml}</m:oMath>"
        f'<w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:tab/><w:t>({number})</w:t></w:r></w:p>'
    )


# ----------------------------------------------------------------------------- the build


class Builder:
    def __init__(self, template: Path) -> None:
        self.macros = load_macros()
        self.tex = Latex(self.macros)
        self.doc = Document(str(template))
        self.body = self.doc.element.body
        self.end = self.body.sectPr
        self.eqs = equations()
        self.eq_number = 0

    # -- template surgery

    def clear_template(self) -> tuple:
        children = list(self.body.iterchildren())
        breaks = [
            c
            for c in children
            if c.tag == qn("w:p") and c.find(qn("w:pPr") + "/" + qn("w:sectPr")) is not None
        ]
        if len(breaks) != 3:
            raise BuildError("the template's sections are not the expected three")
        front_end, body_end, refs_end = breaks
        two_col = copy.deepcopy(body_end.find(qn("w:pPr")).find(qn("w:sectPr")))
        one_col = copy.deepcopy(refs_end.find(qn("w:pPr")).find(qn("w:sectPr")))
        tables = [c for c in children if c.tag == qn("w:tbl")]
        author_table = copy.deepcopy(tables[-1])
        last_para = copy.deepcopy(children[-2])
        start = children.index(front_end) + 1
        for c in children[start:]:
            if c is not self.end:
                self.body.remove(c)
        for rel_id, rel in list(self.doc.part.rels.items()):
            if rel.reltype.endswith("/image"):
                used = self.doc.element.xpath(f'.//*[@r:embed="{rel_id}"]')
                if not used:
                    self.doc.part.drop_rel(rel_id)
        return two_col, one_col, author_table, last_para

    def add(self, xml_or_el) -> object:
        el = parse_xml(xml_or_el) if isinstance(xml_or_el, str) else xml_or_el
        self.end.addprevious(el)
        return el

    def blank(self) -> None:
        self.add(para_xml("Tekst", [], TEXT_PPR))

    def section_break(self, sect) -> None:
        p = self.add(para_xml("Tekst", [], TEXT_PPR))
        p.find(qn("w:pPr")).append(copy.deepcopy(sect))

    # -- front matter

    def front_matter(
        self, title: str, authors: list[str], keywords: list[str], abstract: list[Run]
    ) -> None:
        children = list(self.body.iterchildren())
        paras = [c for c in children if c.tag == qn("w:p")]
        title_p = next(
            p for p in paras if "HYBRID" in "".join(t.text or "" for t in p.iter(qn("w:t")))
        )
        texts = list(title_p.iter(qn("w:t")))
        texts[0].text = title.upper()
        for t in texts[1:]:
            t.text = ""

        def para_text(p) -> str:
            return "".join(t.text or "" for t in p.iter(qn("w:t")))

        author_ps = [
            p for p in paras if para_text(p) in ("Suman Lata1", "Sachit Rathi", "Dinesh Sheoran")
        ]
        if len(author_ps) != 3:
            raise BuildError("the template's author lines were not found")
        plain = author_ps[1]
        anchor = author_ps[-1]
        for p in author_ps:
            if p is not anchor:
                p.getparent().remove(p)
        for name in authors:
            p = copy.deepcopy(plain)
            ts = list(p.iter(qn("w:t")))
            ts[0].text = name
            if name == CORRESPONDING:
                sup = copy.deepcopy(ts[0].getparent())
                rpr = sup.find(qn("w:rPr"))
                rpr.append(parse_xml(f'<w:vertAlign {NS} w:val="superscript"/>'))
                sup.find(qn("w:t")).text = "1"
                ts[0].getparent().addnext(sup)
            anchor.addprevious(p)
        anchor.getparent().remove(anchor)

        table = next(
            c
            for c in children
            if c.tag == qn("w:tbl")
            and "Keywords:" in "".join(t.text or "" for t in c.iter(qn("w:t")))
        )
        for t in list(table.iter(qn("w:t"))):
            if t.text and t.text.startswith("Speech Emotion"):
                t.text = "; ".join(keywords) + "."
            elif t.text and t.text.startswith("A machine that talks"):
                p = t.getparent().getparent()
                template_run = t.getparent()
                for r in abstract:
                    new = copy.deepcopy(template_run)
                    new.find(qn("w:t")).text = r.text
                    new.find(qn("w:t")).set(
                        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                    )
                    if r.vert:
                        new.find(qn("w:rPr")).append(
                            parse_xml(f'<w:vertAlign {NS} w:val="{r.vert}"/>')
                        )
                    if not r.italic:
                        rpr = new.find(qn("w:rPr"))
                        rpr.remove(rpr.find(qn("w:i")))
                        rpr.insert(0, parse_xml(f'<w:i {NS} w:val="0"/>'))
                    p.append(new)
                p.remove(template_run)
        # The template's QR picture carries a path from the journal's own computer.
        for pr in table.iter(
            "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr",
            "{http://schemas.openxmlformats.org/drawingml/2006/picture}cNvPr",
        ):
            if "qr-code" in pr.get("descr", ""):
                pr.set("descr", "QR code")
        leftover = [
            t.text
            for t in table.iter(qn("w:t"))
            if t.text and ("Speech" in t.text or "machine" in t.text)
        ]
        if leftover:
            raise BuildError("the template's keywords or abstract were not replaced")

    # -- body

    def figure(self, key: str, number: int, two_col, one_col) -> None:
        fig = FIGURES[key]
        if not fig.path.exists():
            raise BuildError(f"missing figure {fig.path}")
        if fig.wide:
            self.section_break(two_col)
        p = self.add(para_xml("Slika", [], '<w:keepNext/><w:spacing w:before="80" w:after="0"/>'))
        width = PAGE_EMU if fig.wide else COLUMN_EMU
        Paragraph(p, self.doc._body).add_run().add_picture(str(fig.path), width=Emu(width))
        caption = [Run(f"Figure {number}. ", bold=True), *self.tex.runs(self.resolve(fig.caption))]
        self.add(
            para_xml(
                "Teksispodslike",
                caption,
                '<w:keepLines/><w:spacing w:before="80" w:after="0"/>',
                explicit=True,
            )
        )
        self.blank()
        if fig.wide:
            self.section_break(one_col)

    def equation(self, key: str) -> None:
        self.eq_number += 1
        self.add(equation_xml(self.eqs[key], self.eq_number))

    def table(self, tex: str, two_col, one_col) -> None:
        caption_raw, _ = self.tex.group(tex, tex.index("\\caption") + len("\\caption"))
        caption_raw = re.sub(r"\s+", " ", caption_raw)
        first, _, note = caption_raw.partition(". ")
        start = tex.index("\\begin{tabular}") + len("\\begin{tabular}")
        _, start = self.tex.group(tex, start)
        tabular = tex[start : tex.index("\\end{tabular}")]
        rows: list[list[str] | str] = []
        for raw in re.split(r"\\\\", tabular):
            raw = re.sub(r"\\(toprule|midrule|bottomrule)", "", raw).strip()
            if not raw:
                continue
            if raw.startswith("\\multicolumn"):
                i = len("\\multicolumn")
                _, i = self.tex.group(raw, i)
                _, i = self.tex.group(raw, i)
                content, _ = self.tex.group(raw, i)
                rows.append(content)
            else:
                rows.append([c.strip() for c in raw.split("&")])
        self.section_break(two_col)
        cap = [Run("Table 1. ", bold=True), *self.tex.runs(self.resolve(first + "."))]
        self.add(
            para_xml(
                "Tekstiznadtabele",
                cap,
                '<w:keepNext/><w:spacing w:before="0" w:after="80"/>',
                explicit=True,
            )
        )
        widths = [560, 3050, 1950, 480, 560, 1009, 1030, 1000]
        if sum(widths) != PAGE_TWIPS:
            raise BuildError("table widths do not fill the page")
        cell_ppr = (
            '<w:keepNext/><w:spacing w:before="20" w:after="60" w:line="240" w:lineRule="auto"/>'
        )

        def cell(runs: list[Run], width: int, span: int = 1) -> str:
            grid = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
            body = "".join(run_xml(r, 16) for r in runs)
            return (
                f'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="{width}"/>{grid}</w:tcPr>'
                f"<w:p><w:pPr>{cell_ppr}</w:pPr>{body}</w:p></w:tc>"
            )

        row_xml = []
        for n, row in enumerate(rows):
            header = "<w:tblHeader/>" if n == 0 else ""
            tr = (
                '<w:tr><w:trPr><w:trHeight w:val="250" w:hRule="atLeast"/>'
                f"{header}<w:cantSplit/></w:trPr>"
            )
            if isinstance(row, str):
                tr += cell(self.tex.runs(self.resolve(row)), PAGE_TWIPS, len(widths))
            else:
                if len(row) != len(widths):
                    raise BuildError(f"table row with {len(row)} cells: {row}")
                for text, width in zip(row, widths, strict=True):
                    runs = self.tex.runs(self.resolve(text))
                    if n == 0:
                        runs = [Run(r.text, r.italic, True, r.vert) for r in runs]
                    tr += cell(runs, width)
            row_xml.append(tr + "</w:tr>")
        borders = "".join(
            f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        self.add(
            f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{PAGE_TWIPS}" w:type="dxa"/>'
            f'<w:jc w:val="center"/><w:tblBorders>{borders}</w:tblBorders>'
            '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="28" w:type="dxa"/>'
            '<w:left w:w="57" w:type="dxa"/><w:bottom w:w="28" w:type="dxa"/>'
            '<w:right w:w="57" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" '
            'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(row_xml)}</w:tbl>"
        )
        self.add(
            para_xml(
                "Tekst",
                self.tex.runs(self.resolve(note)),
                '<w:ind w:firstLine="0"/><w:spacing w:before="60"/>',
                18,
            )
        )
        self.blank()
        self.section_break(one_col)

    # -- cross-references and citations

    def resolve(self, s: str) -> str:
        s = re.sub(r"\\PESref\{(\w+)\}", lambda m: f"Figure~{self.fig_no[m.group(1)]}", s)
        s = re.sub(r"Figs\.~", "Figures~", s)
        s = re.sub(r"Fig\.~", "Figure~", s)

        def ref(m: re.Match) -> str:
            label = m.group(1)
            if label in LABEL_FIGURE:
                return str(self.fig_no[LABEL_FIGURE[label]])
            if label == "tab:tests":
                return "1"
            if label in self.sec_no:
                return self.sec_no[label]
            raise BuildError(f"unresolved reference {label}")

        s = re.sub(r"\\ref\{([^}]+)\}", ref, s)

        def narrative(m: re.Match) -> str:
            keys = [k.strip() for k in m.group(2).split(",")]
            name = f"{m.group(1)} et al."
            if any(self.bib.label(k) == name for k in keys):
                return self.bib.narrative(name, keys)
            return f"{name} {self.bib.parenthetical(keys)}"

        s = re.sub(r"\b([A-Z][\w'-]+) et al\.(?:\\ |~| )?\\cite\{([^}]*)\}", narrative, s)
        s = re.sub(
            r"(?:~|\s)?\\cite\{([^}]*)\}",
            lambda m: "~" + self.bib.parenthetical([k.strip() for k in m.group(1).split(",")]),
            s,
        )
        return s

    def build(self, out: Path) -> dict:
        main = strip_comments((PAPER / "main.tex").read_text(encoding="utf-8"))
        title_raw, _ = self.tex.group(main, main.index("\\title") + len("\\title"))
        title = self.tex.plain(title_raw.replace("\\\\", " "))
        authors_raw, _ = self.tex.group(
            main, main.index("\\IEEEauthorblockN") + len("\\IEEEauthorblockN")
        )
        authors = [a.strip() for a in authors_raw.split(",")]
        if CORRESPONDING not in authors:
            raise BuildError("the corresponding author is not among the authors")
        affil_raw, _ = self.tex.group(
            main, main.index("\\IEEEauthorblockA") + len("\\IEEEauthorblockA")
        )
        affil = [self.tex.plain(a) for a in affil_raw.split("\\\\")]
        kw_raw = environment(main, "IEEEkeywords")[0].group(1)
        keywords = [self.tex.plain(k.strip()) for k in kw_raw.split(",")]
        keywords = [k[0].upper() + k[1:] for k in keywords]

        text = "\n\n".join(
            normalise((PAPER / "sections" / f"{n}.tex").read_text(encoding="utf-8"))
            for n in SECTIONS
        )
        statements = re.findall(
            r"\\section\*\{([^}]*)\}(.*?)(?=\\section\*|\\bibliographystyle)", main, re.S
        )
        text += "".join(f"\n\n\\section*{{{h}}}\n\n{normalise(b)}" for h, b in statements)
        for anchor, replacement in EDITS:
            if text.count(anchor) != 1:
                raise BuildError(f"anchor found {text.count(anchor)} times: {anchor[:60]!r}")
            text = text.replace(anchor, replacement)
        for m in environment(text, "figure"):
            label = re.search(r"\\label\{([^}]+)\}", m.group(1)).group(1)
            if label not in LABEL_FIGURE:
                raise BuildError(f"figure {label} has no counterpart here")
        text = re.sub(
            r"\\begin\{figure\}.*?\\label\{([^}]+)\}.*?\\end\{figure\}",
            lambda m: f"\n\n\\PESfig{{{LABEL_FIGURE[m.group(1)]}}}\n\n",
            text,
            flags=re.S,
        )
        tables = environment(text, "table*")
        if len(tables) != 1:
            raise BuildError("expected one table")
        table_tex = tables[0].group(0)
        text = text.replace(table_tex, "\n\n\\PEStable\n\n")
        text = re.sub(
            r"\\begin\{equation\}.*?\\end\{equation\}",
            lambda _: "\n\\PESeq{alc}\n",
            text,
            flags=re.S,
        )

        # Numbering pass: sections, labels and figures in reading order.
        self.sec_no: dict[str, str] = {}
        self.fig_no: dict[str, int] = {}
        sec = sub = 0
        last = ""
        for m in re.finditer(
            r"\\(section|subsection)\{[^}]*\}|\\label\{([^}]+)\}|\\PESfig\{(\w+)\}", text
        ):
            if m.group(1) == "section":
                sec, sub = sec + 1, 0
                last = str(sec)
            elif m.group(1) == "subsection":
                sub += 1
                last = f"{sec}.{sub}"
            elif m.group(2):
                self.sec_no[m.group(2)] = last
            else:
                self.fig_no[m.group(3)] = len(self.fig_no) + 1
        unused = set(FIGURES) - set(self.fig_no)
        if unused:
            raise BuildError(f"figures never placed: {unused}")

        keys: list[str] = []
        for blob in [text, *(f.caption for f in FIGURES.values())]:
            for m in re.findall(r"\\cite\{([^}]*)\}", blob):
                keys += [k.strip() for k in m.split(",") if k.strip() not in keys]
        abstract_tex = normalise((PAPER / "sections" / "abstract.tex").read_text(encoding="utf-8"))
        keys += [k for m in re.findall(r"\\cite\{([^}]*)\}", abstract_tex) for k in m.split(",")]
        self.bib = Bibliography(list(dict.fromkeys(keys)))

        two_col, one_col, author_table, last_para = self.clear_template()
        self.front_matter(
            title, authors, keywords, self.tex.runs(self.resolve(abstract_tex), italic=True)
        )

        blocks = re.split(
            r"(\\section\*?\{[^}]*\}|\\subsection\{[^}]*\}|\\PESfig\{\w+\}|\\PESeq\{\w+\}|\\PEStable|\n\n)",
            text,
        )
        sec = sub = 0
        pending_gap = False
        first = True
        for block in blocks:
            if block is None:
                continue
            if block == "\n\n":
                pending_gap = True
                continue
            block = block.strip()
            if not block:
                continue
            m = re.fullmatch(r"\\(section\*?|subsection)\{([^}]*)\}", block)
            if m:
                kind, head = m.groups()
                head = self.tex.plain(head)
                if kind == "section":
                    sec, sub = sec + 1, 0
                    if not first and not self.last_is_blank():
                        self.blank()
                    self.add(
                        para_xml(
                            "Naslovpoglavlja",
                            [Run(f"{sec}. {head.upper()}")],
                            '<w:numPr><w:numId w:val="0"/></w:numPr>',
                            22,
                        )
                    )
                    self.blank()
                elif kind == "section*":
                    if not self.last_is_blank():
                        self.blank()
                    self.add(
                        para_xml(
                            "Naslovpoglavlja",
                            [Run(head.upper())],
                            '<w:numPr><w:numId w:val="0"/></w:numPr>',
                            22,
                        )
                    )
                    self.blank()
                else:
                    sub += 1
                    if not self.last_is_blank():
                        self.blank()
                    self.add(
                        para_xml(
                            "Naslovpodpoglavlja",
                            [Run(f"{sec}.{sub} {title_case(head)}")],
                            '<w:numPr><w:numId w:val="0"/></w:numPr>',
                            22,
                        )
                    )
                first = False
                pending_gap = False
                continue
            m = re.fullmatch(r"\\PESfig\{(\w+)\}", block)
            if m:
                self.figure(m.group(1), self.fig_no[m.group(1)], two_col, one_col)
                pending_gap = False
                continue
            m = re.fullmatch(r"\\PESeq\{(\w+)\}", block)
            if m:
                self.equation(m.group(1))
                pending_gap = False
                continue
            if block == "\\PEStable":
                self.table(table_tex, two_col, one_col)
                pending_gap = False
                continue
            if pending_gap and not self.last_is_blank():
                self.blank()
            pending_gap = False
            items = environment(block, "enumerate")
            if items:
                before = block[: items[0].start()].strip()
                if before:
                    self.add(para_xml("Tekst", self.tex.runs(self.resolve(before)), TEXT_PPR))
                parts = [p.strip() for p in items[0].group(1).split("\\item") if p.strip()]
                for n, part in enumerate(parts, 1):
                    runs = [Run(f"{n}.\t"), *self.tex.runs(self.resolve(part))]
                    self.add(
                        para_xml(
                            "Tekst",
                            runs,
                            LIST_PPR,
                        )
                    )
                continue
            self.add(para_xml("Tekst", self.tex.runs(self.resolve(block)), TEXT_PPR))

        self.section_break(two_col)
        self.blank()
        self.add(
            f'<w:p {NS}><w:pPr><w:jc w:val="both"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:pPr>'
            '<w:r><w:rPr><w:b/><w:bCs/><w:noProof/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
            "<w:t>References:</w:t></w:r></w:p>"
        )
        for key in self.bib.order():
            runs = [Run(t, italic=it) for t, it in self.bib.reference(key)]
            self.add(
                para_xml(
                    "BodyText",
                    runs,
                    REFERENCE_PPR,
                )
            )
        self.blank()
        self.add(self.author_blocks(author_table, authors, affil))
        self.section_break(one_col)
        self.add(last_para)

        self.properties(title, authors, keywords)
        self.doc.save(str(out))
        scrub(out)
        return {
            "figures": self.fig_no,
            "references": len(self.bib.entries),
            "equations": self.eq_number,
        }

    def last_is_blank(self) -> bool:
        prev = self.end.getprevious()
        return (
            prev is not None
            and prev.tag == qn("w:p")
            and not "".join(t.text or "" for t in prev.iter(qn("w:t")))
            and prev.find(".//" + qn("w:drawing")) is None
            and prev.find(".//" + qn("w:sectPr")) is None
        )

    def author_blocks(self, table, authors: list[str], affil: list[str]):
        """The template's closing author table, one block per author, three to a row."""
        rows = table.findall(qn("w:tr"))
        cell_template = copy.deepcopy(rows[0].findall(qn("w:tc"))[0])
        empty_cell = copy.deepcopy(rows[1].findall(qn("w:tc"))[1])
        row_template = copy.deepcopy(rows[0])
        for r in rows:
            table.remove(r)
        parts = [p.strip() for a in affil for p in a.split(",") if p.strip()]
        lines = []
        for n, part in enumerate(parts):
            lines += split_line(part + ("," if n < len(parts) - 1 else ""), 30)
        for start in range(0, len(authors), 3):
            row = copy.deepcopy(row_template)
            for tc in row.findall(qn("w:tc")):
                row.remove(tc)
            for name in authors[start : start + 3]:
                tc = copy.deepcopy(cell_template)
                ps = tc.findall(qn("w:p"))
                name_p, line_p = ps[0], ps[1]
                for p in ps:
                    tc.remove(p)
                p = copy.deepcopy(name_p)
                p.find(".//" + qn("w:t")).text = name
                tc.append(p)
                email = EMAILS.get(name)
                for text in [*lines, email or EMAIL_PLACEHOLDER]:
                    p = copy.deepcopy(line_p)
                    p.find(".//" + qn("w:t")).text = text
                    if text == EMAIL_PLACEHOLDER:
                        rpr = p.find(qn("w:r") + "/" + qn("w:rPr"))
                        rpr.append(parse_xml(f'<w:color {NS} w:val="FF0000"/>'))
                    tc.append(p)
                row.append(tc)
            while len(row.findall(qn("w:tc"))) < 3:
                row.append(copy.deepcopy(empty_cell))
            table.append(row)
        return table

    def properties(self, title: str, authors: list[str], keywords: list[str]) -> None:
        cp = self.doc.core_properties
        cp.title = title
        cp.author = ", ".join(authors)
        cp.last_modified_by = authors[0]
        cp.keywords = "; ".join(keywords)
        cp.subject = "Proceedings on Engineering Sciences"
        cp.comments = ""
        cp.category = ""
        cp.modified = datetime.now(UTC).replace(microsecond=0, tzinfo=None)


def split_line(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    return [*lines, line]


APP_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    "<Template>Normal</Template><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
    "<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>"
    "<HyperlinksChanged>false</HyperlinksChanged></Properties>"
)
CUSTOM_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
)


def running_head(xml: str) -> str:
    """Put the first author's surname where the template says "1st author"."""
    for old, new in (("1", RUNNING_AUTHOR), ("st", ""), (" author", "")):
        pattern = re.compile(r"(<w:t(?: [^>]*)?>)" + re.escape(old) + r"(</w:t>)")
        xml = pattern.sub(lambda m, new=new: m.group(1) + new + m.group(2), xml, count=1)
    return xml


def scrub(path: Path) -> None:
    """Drop the template's document statistics, links and review metadata."""
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = APP_XML.encode()
            elif item.filename.startswith("word/header") and item.filename.endswith(".xml"):
                data = running_head(data.decode()).encode()
            elif item.filename == "docProps/custom.xml":
                data = CUSTOM_XML.encode()
            dst.writestr(item, data)
    tmp.replace(path)


def to_pdf(docx: Path, pdf: Path) -> None:
    """LibreOffice, with the template's Times New Roman given to a fresh profile.

    Run headless, LibreOffice on macOS does not see the system's fonts and substitutes
    Liberation Serif; fonts placed in the profile's own font folder are loaded.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fonts = Path(tmp) / "profile" / "user" / "fonts"
        fonts.mkdir(parents=True)
        for f in FONT_DIR.glob("Times New Roman*.ttf"):
            shutil.copy(f, fonts)
        outdir = Path(tmp) / "out"
        subprocess.run(
            [
                SOFFICE,
                f"-env:UserInstallation=file://{Path(tmp) / 'profile'}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(docx),
            ],
            check=True,
            capture_output=True,
        )
        shutil.copy(outdir / (docx.stem + ".pdf"), pdf)


# ----------------------------------------------------------------------------- overlap check


def words_of(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.findall(r"[a-z0-9]+(?:['’-][a-z0-9]+)*", text)


def docx_body_text(path: Path) -> str:
    doc = Document(str(path))
    body = doc.element.body
    return "\n".join("".join(t.text or "" for t in p.iter(qn("w:t"))) for p in body.iter(qn("w:p")))


def overlap(ours: str, theirs: str, n: int = 8) -> list[str]:
    a, b = words_of(ours), words_of(theirs)
    grams = {tuple(b[i : i + n]) for i in range(len(b) - n + 1)}
    hits, i = [], 0
    while i <= len(a) - n:
        if tuple(a[i : i + n]) in grams:
            j = i + n
            while j < len(a) and tuple(a[j - n + 1 : j + 1]) in grams:
                j += 1
            hits.append(" ".join(a[i:j]))
            i = j
        else:
            i += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--pdf", action="store_true", help="also convert with LibreOffice")
    parser.add_argument(
        "--overlap", nargs="+", type=Path, help="texts to check 8-word overlap against"
    )
    args = parser.parse_args()
    if not args.template.exists():
        print(f"template not found: {args.template}", file=sys.stderr)
        return 1
    try:
        info = Builder(args.template).build(OUT_DOCX)
    except BuildError as err:
        print(f"build failed: {err}", file=sys.stderr)
        return 1
    print(f"wrote {OUT_DOCX.relative_to(ROOT)}: {info}")
    if args.pdf:
        to_pdf(OUT_DOCX, OUT_PDF)
        print(f"wrote {OUT_PDF.relative_to(ROOT)}")
    for path in OUT_DOCX, OUT_PDF:
        if path.exists() and path.stat().st_size > 5_000_000:
            print(f"{path.name} is over 5 MB", file=sys.stderr)
            return 1
    if args.overlap:
        ours = docx_body_text(OUT_DOCX)
        for other in args.overlap:
            if other.suffix == ".docx":
                theirs = docx_body_text(other)
            else:
                theirs = other.read_text(encoding="utf-8", errors="replace")
            hits = overlap(ours, theirs)
            print(f"{other.name}: {len(hits)} runs of 8 or more words in common")
            for h in hits:
                print(f"  {h}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
