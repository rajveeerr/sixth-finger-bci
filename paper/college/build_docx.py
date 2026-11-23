"""Build an editable Word version of the college paper on IEEE's own Word template.

uv run --with python-docx==1.2.0 --with pymupdf==1.26.5 python paper/college/build_docx.py
uv run --with python-docx==1.2.0 --with pymupdf==1.26.5 python paper/college/build_docx.py \
    --pdf --check

The text comes from paper/college/*.tex, every number from paper/generated/numbers.tex, and the
numbering of sections, figures, tables, equations and citations from a fresh Tectonic run of
paper/college/main.tex, whose .aux and .bbl give the same numbers and reference list as the
PDF. Figures are drawn by LaTeX, one to a page at their printed size, and rasterised. The styles
are those of IEEE's conference template (paper title, Heading 1 in roman numerals, figure
caption, table head, references), set to one column and the sizes of the LaTeX paper.
"""

from __future__ import annotations

import argparse
import copy
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import fitz
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.text.paragraph import Paragraph

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
ROOT = PAPER.parent
MAIN = HERE / "main.tex"
NUMBERS = PAPER / "generated" / "numbers.tex"
REFERENCE_PDF = PAPER / "build" / "college.pdf"
OUT_DOCX = HERE / "sixth-finger-bci-ieee.docx"
# The LibreOffice rendering is only for checking; the LaTeX PDF stays the reference.
OUT_PDF = PAPER / "build" / "college-docx.pdf"
SECTIONS = [
    "introduction",
    "literature",
    "methodology",
    "architecture",
    "experiments",
    "ablation",
    "discussion",
    "conclusion",
]
TEMPLATE_URL = "https://ieee-org.widen.net/content/ge5anzdecd/original/conference-template-a4.docx"
DEFAULT_TEMPLATE = Path.home() / "Downloads" / "conference-template-a4.docx"
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
FONT_DIR = Path("/System/Library/Fonts/Supplemental")
PROFILE_FONTS = ["Times New Roman*.ttf", "Courier New*.ttf", "STIXTwoMath.otf", "STIXGeneral*.otf"]
TNR = FONT_DIR / "Times New Roman.ttf"
DPI = 600

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = f'xmlns:w="{W_NS}" xmlns:m="{M_NS}"'

# The LaTeX page: US letter, 514 pt of text, 50 lines of 13.33 pt, in twips (1/20 pt).
PAGE_W, PAGE_H = 12240, 15840
MARGIN_LR, MARGIN_TOP, MARGIN_BOTTOM, HEADER = 980, 1110, 1390, 500
TEXT_W = PAGE_W - 2 * MARGIN_LR
TEXT_PT = TEXT_W / 20


class BuildError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- the template

STRICT = {
    "http://purl.oclc.org/ooxml/wordprocessingml/main": W_NS,
    "http://purl.oclc.org/ooxml/officeDocument/math": M_NS,
    "http://purl.oclc.org/ooxml/drawingml/main": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://purl.oclc.org/ooxml/drawingml/picture": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://purl.oclc.org/ooxml/officeDocument/docPropsVTypes": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    "http://purl.oclc.org/ooxml/officeDocument/extendedProperties": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "http://purl.oclc.org/ooxml/officeDocument/customXml": "http://schemas.openxmlformats.org/officeDocument/2006/customXml",
    "http://purl.oclc.org/ooxml/officeDocument/sharedTypes": "http://schemas.openxmlformats.org/officeDocument/2006/sharedTypes",
    "http://purl.oclc.org/ooxml/officeDocument/bibliography": "http://schemas.openxmlformats.org/officeDocument/2006/bibliography",
}
STRICT_RELS = "http://purl.oclc.org/ooxml/officeDocument/relationships"
TRANSITIONAL_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def fetch_template(path: Path, workdir: Path) -> Path:
    if path.exists():
        return path
    target = workdir / "conference-template-a4.docx"
    request = urllib.request.Request(TEMPLATE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())
    if not zipfile.is_zipfile(target):
        raise BuildError(f"could not download IEEE's template from {TEMPLATE_URL}")
    return target


def to_transitional(xml: str) -> str:
    """IEEE saves its template as Strict Open XML, which python-docx and LibreOffice do not
    read; this rewrites it in the Transitional vocabulary Word itself would write."""
    xml = xml.replace(STRICT_RELS, TRANSITIONAL_RELS)
    for old, new in STRICT.items():
        xml = xml.replace(old, new)
    left = re.findall(r"http://purl\.oclc\.org/ooxml/[\w/]+", xml)
    if left:
        raise BuildError(f"unmapped Strict namespaces: {sorted(set(left))}")
    xml = re.sub(r' conformance="strict"', "", xml)
    xml = re.sub(
        r'(\sw:[A-Za-z]+)="(-?\d+(?:\.\d+)?)pt"',
        lambda m: f'{m.group(1)}="{round(float(m.group(2)) * 20)}"',
        xml,
    )
    xml = re.sub(r'(\sw:(?:val|percent))="(\d+)%"', r'\1="\2"', xml)
    xml = re.sub(r"(<w:ind\b[^>]*?)\sw:start=", r"\1 w:left=", xml)
    xml = re.sub(r"(<w:ind\b[^>]*?)\sw:end=", r"\1 w:right=", xml)
    xml = re.sub(r'(<w:(?:jc|tab|lvlJc)\b[^>]*?w:val=)"start"', r'\1"left"', xml)
    xml = re.sub(r'(<w:(?:jc|tab|lvlJc)\b[^>]*?w:val=)"end"', r'\1"right"', xml)
    return xml


def transitional_copy(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                data = to_transitional(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)


# ----------------------------------------------------------------------------- LaTeX run


def tectonic(tex: Path, outdir: Path) -> None:
    result = subprocess.run(
        ["tectonic", "-X", "compile", str(tex), "--outdir", str(outdir), "--keep-intermediates"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        errors = [ln for ln in result.stderr.splitlines() if ln.startswith(("error", "!", "l."))]
        raise BuildError(f"tectonic failed on {tex.name}:\n" + "\n".join(errors[:20]))


def read_aux(aux: Path) -> tuple[dict[str, str], dict[str, int]]:
    labels: dict[str, str] = {}
    cites: dict[str, int] = {}
    for line in aux.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\\newlabel\{([^}]+)\}\{\{(.*?)\}\{\d+\}", line)
        if m:
            value = re.sub(r"\\mbox\s*\{([^}]*)\}", r"\1", m.group(2)).strip("{} ")
            labels[m.group(1)] = value
        m = re.match(r"\\bibcite\{([^}]+)\}\{(\d+)\}", line)
        if m:
            cites[m.group(1)] = int(m.group(2))
    return labels, cites


def read_bbl(bbl: Path) -> list[tuple[str, str]]:
    text = bbl.read_text(encoding="utf-8")
    text = text[text.index("\\BIBdecl") + len("\\BIBdecl") : text.index("\\end{thebibliography}")]
    entries = []
    for chunk in re.split(r"\\bibitem\{", text)[1:]:
        key, _, body = chunk.partition("}")
        body = re.sub(r"\\hskip [^\\]*\\relax", " ", body)
        body = re.sub(
            r"\\BIBentry(?:ALT|STD)interwordspacing|\\newblock|\\BIBforeignlanguage\{\w+\}",
            "",
            body,
        )
        entries.append((key, re.sub(r"\s+", " ", body).strip()))
    return entries


def load_macros() -> dict[str, str]:
    macros: dict[str, str] = {}
    for line in NUMBERS.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", line.strip())
        if m:
            macros[m.group(1)] = m.group(2)
    if not macros:
        raise BuildError(f"no macros in {NUMBERS}")
    return macros


# ----------------------------------------------------------------------------- LaTeX to runs


@dataclass(frozen=True)
class Run:
    text: str
    italic: bool = False
    bold: bool = False
    mono: bool = False
    vert: str = ""
    size: int = 0  # half-points; 0 keeps the paragraph style's size


PLAIN = Run("")
GREEK = {
    "alpha": "α",
    "beta": "β",
    "omega": "ω",
    "mu": "μ",
    "Sigma": "Σ",
    "ell": "ℓ",
}
MATH_SYMBOLS = {
    "leq": "≤",
    "geq": "≥",
    "in": "∈",
    "times": "×",
    "dagger": "†",
    "infty": "∞",
    "pm": "±",
    "approx": "≈",
    "cdot": "·",
    "star": "⋆",
    "top": "⊤",
    "ldots": "…",
}
RELATIONS = {"=", "<", ">", "≤", "≥", "∈", "≈"}
BINARY = {"+", "−", "×", "±", "·"}
UPRIGHT_FUNCS = {"ln", "log", "min", "max", "exp", "arg"}
BLACKBOARD = {"R": "ℝ"}
CALLIGRAPHIC = {"L": "ℒ"}
SILENT = {
    "par",
    "raggedright",
    "noindent",
    "centering",
    "footnotesize",
    "small",
    "scriptsize",
    "relax",
    "left",
    "right",
}


def compress_cites(numbers: list[int]) -> str:
    """The cite package's style: [4], [5] and [21]–[23]."""
    nums = sorted(set(numbers))
    groups: list[list[int]] = []
    for n in nums:
        if groups and n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    parts = []
    for g in groups:
        if len(g) >= 3:
            parts.append(f"[{g[0]}]–[{g[-1]}]")
        else:
            parts += [f"[{n}]" for n in g]
    return ", ".join(parts)


class Tex:
    """The paper's LaTeX subset to runs; anything unknown stops the build."""

    def __init__(self, macros: dict[str, str], labels: dict[str, str], cites: dict[str, int]):
        self.macros = macros
        self.labels = labels
        self.cites = cites
        self.used_macros: set[str] = set()

    def resolve(self, s: str) -> str:
        def ref(m: re.Match) -> str:
            if m.group(1) not in self.labels:
                raise BuildError(f"unresolved reference {m.group(1)}")
            return self.labels[m.group(1)]

        def cite(m: re.Match) -> str:
            keys = [k.strip() for k in m.group(1).split(",")]
            missing = [k for k in keys if k not in self.cites]
            if missing:
                raise BuildError(f"citations not in the bibliography: {missing}")
            return compress_cites([self.cites[k] for k in keys])

        s = re.sub(r"\\ref\{([^}]+)\}", ref, s)
        return re.sub(r"\\cite\{([^}]+)\}", cite, s)

    @staticmethod
    def group(s: str, i: int) -> tuple[str, int]:
        while i < len(s) and s[i] == " ":
            i += 1
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

    @staticmethod
    def optional(s: str, i: int) -> tuple[str, int]:
        if i < len(s) and s[i] == "[":
            j = s.index("]", i)
            return s[i + 1 : j], j + 1
        return "", i

    def runs(
        self, s: str, base: Run = PLAIN, math: bool = False, script: bool = False
    ) -> list[Run]:
        out: list[Run] = []

        def add(text: str, **kw) -> None:
            out.append(replace(base, text=text, **kw))

        def last_char() -> str:
            for r in reversed(out):
                if r.text.strip():
                    return r.text.strip()[-1]
            return ""

        def operator(sym: str) -> None:
            if script:
                add(sym, italic=False)
                return
            prev = last_char()
            binary = sym in BINARY and prev and prev not in "([{" and prev not in RELATIONS | BINARY
            if sym in RELATIONS or binary:
                add(f" {sym} ", italic=False)
            else:
                add(sym, italic=False)

        i = 0
        while i < len(s):
            c = s[i]
            if c == "\\":
                m = re.match(r"\\([A-Za-z]+)", s[i:])
                if not m:
                    nxt = s[i + 1]
                    i += 2
                    if nxt == ",":
                        add("\u2009", italic=False)
                    elif nxt in "!;:":
                        if nxt != "!":
                            add(" ", italic=False)
                    elif nxt in "%_&#$":
                        add(nxt, italic=False if math else base.italic)
                    elif nxt in "{}":
                        add(nxt, italic=False)
                    elif nxt == " " or nxt == "\\":
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
                        raise BuildError(f"macro \\{name} is still TBD")
                    self.used_macros.add(name)
                    out += self.runs(value, base, math, script)
                elif re.fullmatch(r"(n|rq|ex|dl|demo|eda|audit|runtime)[A-Z]\w*", name):
                    raise BuildError(f"macro \\{name} is not in numbers.tex")
                elif name == "ensuremath":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, base, True, script)
                elif name in ("emph", "textit"):
                    arg, i = self.group(s, i)
                    out += self.runs(arg, replace(base, italic=not base.italic), math, script)
                elif name == "textbf":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, replace(base, bold=True), math, script)
                elif name == "texttt":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, replace(base, mono=True), False, script)
                elif name == "src":
                    arg, i = self.group(s, i)
                    out += self.runs(arg, replace(base, mono=True, size=14), False, script)
                elif name in ("text", "textrm", "mathrm", "operatorname"):
                    arg, i = self.group(s, i)
                    sub = self.runs(arg, replace(base, italic=False), False, script)
                    out += [replace(r, italic=False) for r in sub]
                elif name == "textmu":
                    add("µ", italic=False)
                elif name == "mathbb":
                    arg, i = self.group(s, i)
                    add(BLACKBOARD[arg], italic=False)
                elif name == "mathcal":
                    arg, i = self.group(s, i)
                    add(CALLIGRAPHIC[arg], italic=False)
                elif name in ("bar", "tilde", "hat"):
                    arg, i = self.group(s, i)
                    mark = {"bar": "\u0304", "tilde": "\u0303", "hat": "\u0302"}[name]
                    inner = self.runs(arg, base, True, script)
                    inner[-1] = replace(inner[-1], text=inner[-1].text + mark)
                    out += inner
                elif name == "sqrt":
                    arg, i = self.group(s, i)
                    add("√", italic=False)
                    out += self.runs(arg, base, True, script)
                elif name == "MakeLowercase":
                    arg, i = self.group(s, i)
                    out += [replace(r, text=r.text.lower()) for r in self.runs(arg, base, math)]
                elif name in GREEK:
                    add(GREEK[name], italic=math and name[0].islower())
                elif name in MATH_SYMBOLS:
                    sym = MATH_SYMBOLS[name]
                    if math and (sym in RELATIONS or sym in BINARY):
                        operator(sym)
                    else:
                        add(sym, italic=False)
                elif name in UPRIGHT_FUNCS:
                    add(name, italic=False)
                elif name == "quad":
                    add("\u2003", italic=False)
                elif name == "qquad":
                    add("\u2003\u2003", italic=False)
                elif name in SILENT:
                    pass
                elif name == "label":
                    _, i = self.group(s, i)
                elif name == "url":
                    arg, i = self.group(s, i)
                    add(arg)
                elif name == "v":
                    arg, i = self.group(s, i)
                    add(unicodedata.normalize("NFC", arg + "\u030c"))
                elif name == "hfill":
                    pass
                else:
                    raise BuildError(
                        f"unknown command \\{name} near {s[max(0, i - 40) : i + 20]!r}"
                    )
                continue
            if c == "{":
                arg, i = self.group(s, i)
                out += self.runs(arg, base, math, script)
                continue
            if c == "}":
                raise BuildError(f"stray brace in: {s[max(0, i - 40) : i + 40]!r}")
            if c == "$":
                j = s.index("$", i + 1)
                out += self.runs(s[i + 1 : j], base, True, script)
                i = j + 1
                continue
            if c == "~":
                add("\u00a0")
                i += 1
                continue
            if c == "'" and s.startswith("{\\'", i - 1):
                i += 1
                continue
            if math and c in "^_":
                vert = "superscript" if c == "^" else "subscript"
                i += 1
                while s[i] == " ":
                    i += 1
                if s[i] == "{":
                    arg, i = self.group(s, i)
                elif s[i] == "\\":
                    m = re.match(r"\\([A-Za-z]+)", s[i:])
                    arg, i = s[i : i + len(m.group(0))], i + len(m.group(0))
                else:
                    arg, i = s[i], i + 1
                for r in self.runs(arg, base, True, True):
                    out.append(replace(r, vert=vert))
                continue
            if math:
                if c == "-":
                    operator("−")
                elif c in "=<>+":
                    operator(c)
                elif c == "*":
                    add("∗", italic=False)
                elif c in ",;":
                    add(c + (" " if not script else ""), italic=False)
                elif c.isalpha():
                    add(c, italic=True)
                elif c.isspace():
                    pass
                else:
                    add(c, italic=False)
                i += 1
                continue
            for seq, rep in (("---", "—"), ("--", "–"), ("``", "“"), ("''", "”")):
                if s.startswith(seq, i):
                    add(rep)
                    i += len(seq)
                    break
            else:
                if c == "`":
                    add("‘")
                    i += 1
                elif c == "'":
                    add("’")
                    i += 1
                elif c == "\\'":
                    i += 1
                else:
                    j = i
                    while j < len(s) and s[j] not in "\\{}$~^_-`'":
                        j += 1
                    if j == i:
                        j = i + 1
                    add(s[i:j])
                    i = j
        return merge(out)

    def plain(self, s: str) -> str:
        return "".join(r.text for r in self.runs(self.resolve(s)))


def merge(runs: list[Run]) -> list[Run]:
    out: list[Run] = []
    for r in runs:
        r = replace(r, text=re.sub(r"[ \t\n]+", " ", r.text))
        if not r.text:
            continue
        if out and replace(out[-1], text="") == replace(r, text=""):
            out[-1] = replace(r, text=out[-1].text + r.text)
        else:
            out.append(r)
    joined: list[Run] = []
    for r in out:
        if joined and joined[-1].text.endswith(" ") and r.text.startswith(" "):
            r = replace(r, text=r.text[1:])
        if r.text:
            joined.append(r)
    return joined


def accent_fix(s: str) -> str:
    """{\\'e} and {\\v{s}} style accents of the .bbl to Unicode."""
    marks = {"'": "\u0301", '"': "\u0308", "`": "\u0300", "^": "\u0302", "~": "\u0303"}
    s = re.sub(
        r"\{\\(['\"`^~])\{?([A-Za-z])\}?\}",
        lambda m: unicodedata.normalize("NFC", m.group(2) + marks[m.group(1)]),
        s,
    )
    return re.sub(
        r"\{\\v\{([A-Za-z])\}\}", lambda m: unicodedata.normalize("NFC", m.group(1) + "\u030c"), s
    )


# ----------------------------------------------------------------------------- equations (OMML)


def m_run(text: str, style: str = "") -> str:
    sty = f'<m:rPr><m:sty m:val="{style}"/></m:rPr>' if style else ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<m:r>{sty}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
        f'<w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
        f'<m:t xml:space="preserve">{text}</m:t></m:r>'
    )


class Omml:
    """The display equations' LaTeX to Office Math: fractions, scripts, n-ary operators,
    delimiters, accents and the paper's symbols."""

    NARY: ClassVar[dict[str, str]] = {"int": "∫", "sum": "∑"}
    ACCENTS: ClassVar[dict[str, str]] = {"bar": "\u0305", "tilde": "\u0303", "hat": "\u0302"}
    STOP: ClassVar[set[str]] = {"+", "−", ",", "=", ";", "qquad"}

    def __init__(self, tex: Tex) -> None:
        self.tex = tex

    def tokens(self, s: str) -> list[str]:
        s = s.replace("\\arg\\max", "\\argmax")
        toks = []
        i = 0
        while i < len(s):
            c = s[i]
            if c == "\\":
                m = re.match(r"\\([A-Za-z]+)", s[i:])
                if m:
                    name = m.group(1)
                    i += len(m.group(0))
                    if name in self.tex.macros:
                        if s.startswith("{}", i):
                            i += 2
                        toks += self.tokens(self.tex.macros[name].replace("\\ensuremath", ""))
                        self.tex.used_macros.add(name)
                    else:
                        toks.append("\\" + name)
                else:
                    toks.append(s[i : i + 2])
                    i += 2
            elif c.isspace():
                i += 1
            else:
                toks.append(c)
                i += 1
        return toks

    def convert(self, s: str) -> str:
        self.toks = self.tokens(s)
        self.i = 0
        nodes = self.seq()
        if self.i != len(self.toks):
            raise BuildError(f"equation not fully read: {s!r}")
        return "".join(nodes)

    def peek(self) -> str | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> str:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def arg(self) -> str:
        if self.peek() == "{":
            self.take()
            body = self.seq(close="}")
            self.take()
            return "".join(body)
        return "".join(self.atom())

    def raw_group(self) -> str:
        if self.take() != "{":
            raise BuildError("expected a group in an equation")
        depth, out = 1, []
        while True:
            tok = self.take()
            depth += {"{": 1, "}": -1}.get(tok, 0)
            if depth == 0:
                return "".join(out)
            out.append(tok)

    def seq(self, close: str | None = None) -> list[str]:
        items: list[tuple[str, str]] = []  # (xml, kind)
        while self.peek() is not None and self.peek() != close and self.peek() != "\\right":
            items.append(self.item())
        out: list[str] = []
        k = 0
        while k < len(items):
            xml, kind = items[k]
            if kind.startswith("nary:"):
                body, depth = [], 0
                k += 1
                while k < len(items):
                    nxt, nk = items[k]
                    if nk == "(":
                        depth += 1
                    elif nk == ")":
                        depth -= 1
                    if depth == 0 and nk in self.STOP:
                        break
                    body.append(nxt)
                    k += 1
                out.append(xml.replace("<m:e></m:e>", f"<m:e>{''.join(body)}</m:e>"))
                continue
            out.append(xml)
            k += 1
        return out

    def item(self) -> tuple[str, str]:
        tok = self.peek()
        if tok in ("\\int", "\\sum"):
            self.take()
            sub = sup = ""
            while self.peek() in ("_", "^"):
                which = self.take()
                if which == "_":
                    sub = self.arg()
                else:
                    sup = self.arg()
            chr_ = self.NARY[tok[1:]]
            loc = "subSup" if tok == "\\int" else "undOvr"
            xml = (
                f'<m:nary><m:naryPr><m:chr m:val="{chr_}"/><m:limLoc m:val="{loc}"/>'
                + ("" if sup else '<m:supHide m:val="1"/>')
                + f"</m:naryPr><m:sub>{sub}</m:sub><m:sup>{sup}</m:sup><m:e></m:e></m:nary>"
            )
            return xml, "nary:"
        if tok == "\\argmax":
            self.take()
            if self.take() != "_":
                raise BuildError("\\arg\\max needs a subscript here")
            lim = self.arg()
            return (
                f"<m:limLow><m:e>{m_run('arg max', 'p')}</m:e><m:lim>{lim}</m:lim></m:limLow>",
                "func",
            )
        base, kind = self.atom()
        sub = sup = None
        while self.peek() in ("_", "^"):
            which = self.take()
            if which == "_":
                sub = self.arg()
            else:
                sup = self.arg()
        if sub is not None and sup is not None:
            base = (
                f"<m:sSubSup><m:e>{base}</m:e><m:sub>{sub}</m:sub><m:sup>{sup}</m:sup></m:sSubSup>"
            )
        elif sub is not None:
            base = f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"
        elif sup is not None:
            base = f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"
        return base, kind

    def atom(self) -> tuple[str, str]:
        tok = self.take()
        if tok == "{":
            body = self.seq(close="}")
            self.take()
            return "".join(body), "group"
        if tok == "\\frac":
            num = self.arg()
            den = self.arg()
            return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>", "frac"
        if tok == "\\left":
            open_ = self.take()
            body = self.seq()
            if self.take() != "\\right":
                raise BuildError("\\left without \\right")
            close = self.take()
            return (
                f'<m:d><m:dPr><m:begChr m:val="{open_}"/><m:endChr m:val="{close}"/></m:dPr>'
                f"<m:e>{''.join(body)}</m:e></m:d>",
                "delim",
            )
        if tok[1:] in self.ACCENTS:
            inner = self.arg()
            return (
                f'<m:acc><m:accPr><m:chr m:val="{self.ACCENTS[tok[1:]]}"/></m:accPr>'
                f"<m:e>{inner}</m:e></m:acc>",
                "acc",
            )
        if tok in ("\\mathrm", "\\text"):
            text = self.raw_group()
            return m_run(text, "p"), "text"
        if tok == "\\mathbb":
            return m_run(BLACKBOARD[self.raw_group()]), "sym"
        if tok == "\\mathcal":
            return m_run(CALLIGRAPHIC[self.raw_group()]), "sym"
        if tok in ("\\,", "\\;"):
            return m_run("\u2009"), "space"
        if tok == "\\!":
            return "", "space"
        if tok == "\\qquad":
            return m_run("\u2003\u2003"), "qquad"
        if tok == "\\quad":
            return m_run("\u2003"), "space"
        if tok.startswith("\\"):
            name = tok[1:]
            if name in UPRIGHT_FUNCS:
                return m_run(name, "p"), "func"
            if name in GREEK:
                return m_run(GREEK[name]), "sym"
            if name in MATH_SYMBOLS:
                sym = MATH_SYMBOLS[name]
                return m_run(sym), sym
            raise BuildError(f"unknown command {tok} in an equation")
        if tok == "-":
            return m_run("−"), "−"
        if tok in "()":
            return m_run(tok), tok
        if tok in "+=,;":
            return m_run(tok), tok
        return m_run(tok), "char"


# ----------------------------------------------------------------------------- figures


@dataclass
class Fig:
    label: str
    width: str  # LaTeX length of its box
    body: str
    caption: str
    png: bytes = b""
    width_pt: float = 0.0
    height_pt: float = 0.0


def content_bbox(page: fitz.Page) -> fitz.Rect:
    """Everything drawn on the page, white backgrounds aside."""
    rect = fitz.Rect()
    for d in page.get_drawings():
        fill, stroke = d.get("fill"), d.get("color")
        white = fill is not None and min(fill) > 0.99
        if stroke is None and (fill is None or white):
            continue
        pad = (d.get("width") or 0) / 2
        rect |= d["rect"] + (-pad, -pad, pad, pad)
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 1:
            rect |= fitz.Rect(block["bbox"])
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    rect |= fitz.Rect(span["bbox"])
    for img in page.get_image_info():
        rect |= fitz.Rect(img["bbox"])
    if rect.is_empty:
        raise BuildError(f"nothing drawn on figure page {page.number + 1}")
    return fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1) & page.rect


def render_figures(figs: list[Fig], workdir: Path, aux: Path) -> fitz.Document:
    """Typeset every figure alone on a page with the paper's own preamble, then crop and
    rasterise it at its printed size."""
    main = MAIN.read_text(encoding="utf-8")
    preamble = main[: main.index("\\begin{document}")]
    preamble = preamble.replace(
        "\\graphicspath{{../figures/}{../../docs/figures/}}",
        f"\\graphicspath{{{{{PAPER / 'figures'}/}}{{{ROOT / 'docs' / 'figures'}/}}}}",
    )
    preamble = preamble.replace("\\input{../generated/numbers}", f"\\input{{{NUMBERS}}}")
    pages = []
    for fig in figs:
        body = re.sub(
            r"\\input\{(fig-[\w-]+)\}", lambda m: f"\\input{{{HERE / m.group(1)}}}", fig.body
        )
        pages.append(
            f"\\thispagestyle{{empty}}\\noindent\\begin{{minipage}}[t]{{{fig.width}}}\\centering\n"
            f"{body}\n\\end{{minipage}}\n\\clearpage"
        )
    tex = workdir / "figures.tex"
    # The drawings name sections, so they get the paper's own labels.
    labels = [
        ln for ln in aux.read_text(encoding="utf-8").splitlines() if ln.startswith("\\newlabel{")
    ]
    tex.write_text(
        preamble
        + "\\makeatletter\n"
        + "\n".join(labels)
        + "\n\\makeatother\n\\pagestyle{empty}\n\\begin{document}\n"
        + "\n".join(pages)
        + "\n\\end{document}\n",
        encoding="utf-8",
    )
    tectonic(tex, workdir)
    pdf = fitz.open(workdir / "figures.pdf")
    if len(pdf) != len(figs):
        raise BuildError(f"{len(figs)} figures typeset on {len(pdf)} pages")
    for fig, page in zip(figs, pdf, strict=True):
        box = content_bbox(page)
        pix = page.get_pixmap(dpi=DPI, clip=box, alpha=False)
        fig.png = pix.tobytes("png")
        fig.width_pt, fig.height_pt = box.width, box.height
    return pdf


# ----------------------------------------------------------------------------- document parts


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_TNR = fitz.Font(fontfile=str(TNR)) if TNR.exists() else None
_FACES: dict[tuple[bool, bool], fitz.Font] = {}


def text_width(text: str, italic: bool, bold: bool, size: float) -> float:
    """Width in points of text set in Times New Roman."""
    key = (italic, bold)
    if key not in _FACES:
        name = {
            (False, False): "",
            (True, False): " Italic",
            (False, True): " Bold",
            (True, True): " Bold Italic",
        }[key]
        _FACES[key] = fitz.Font(fontfile=str(FONT_DIR / f"Times New Roman{name}.ttf"))
    return _FACES[key].text_length(text, fontsize=size)


def needs_math_font(ch: str) -> bool:
    return _TNR is not None and ch.strip() != "" and not _TNR.has_glyph(ord(ch))


def run_xml(r: Run, extra: str = "") -> str:
    props = extra
    if r.bold:
        props += "<w:b/>"
    if r.italic:
        props += "<w:i/>"
    if r.size:
        props += f'<w:sz w:val="{r.size}"/><w:szCs w:val="{r.size}"/>'
    if r.vert:
        props += f'<w:vertAlign w:val="{r.vert}"/>'
    out = ""
    pieces = re.split(r"(.)", r.text)
    buf, buf_math = "", False
    chunks: list[tuple[str, bool]] = []
    for piece in pieces:
        if not piece:
            continue
        is_math = needs_math_font(piece)
        if buf and is_math != buf_math:
            chunks.append((buf, buf_math))
            buf = ""
        buf += piece
        buf_math = is_math
    if buf:
        chunks.append((buf, buf_math))
    for text, is_math in chunks:
        font = ""
        if is_math:
            font = '<w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
        elif r.mono:
            font = '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
        out += f'<w:r><w:rPr>{font}{props}</w:rPr><w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
    return out


def para_xml(style: str, runs: list[Run] | str, ppr: str = "") -> str:
    if isinstance(runs, str):
        body = runs
    else:
        runs = list(runs)
        if runs:
            runs[0] = replace(runs[0], text=runs[0].text.lstrip())
            runs[-1] = replace(runs[-1], text=runs[-1].text.rstrip())
        body = "".join(run_xml(r) for r in runs if r.text)
    return f'<w:p {NS}><w:pPr><w:pStyle w:val="{style}"/>{ppr}</w:pPr>{body}</w:p>'


def strip_comments(tex: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in tex.splitlines())


def find_env(tex: str, name: str, start: int = 0) -> tuple[int, int, str] | None:
    begin = tex.find(f"\\begin{{{name}}}", start)
    if begin < 0:
        return None
    end = tex.index(f"\\end{{{name}}}", begin)
    body = tex[begin + len(f"\\begin{{{name}}}") : end]
    body = re.sub(r"^\[[^\]]*\]", "", body)
    return begin, end + len(f"\\end{{{name}}}"), body


# ----------------------------------------------------------------------------- styles


def set_style(styles, style_id: str, ppr: str, rpr: str, based_on: str | None = None) -> None:
    style = styles.find(f"{{{W_NS}}}style[@{{{W_NS}}}styleId='{style_id}']")
    if style is None:
        raise BuildError(f"IEEE's template has no style {style_id}")
    for tag in ("pPr", "rPr"):
        old = style.find(qn(f"w:{tag}"))
        if old is not None:
            style.remove(old)
    if based_on is not None:
        old = style.find(qn("w:basedOn"))
        if old is not None:
            style.remove(old)
        if based_on:
            style.find(qn("w:name")).addnext(parse_xml(f'<w:basedOn {NS} w:val="{based_on}"/>'))
    style.append(parse_xml(f"<w:pPr {NS}>{ppr}</w:pPr>"))
    style.append(parse_xml(f"<w:rPr {NS}>{rpr}</w:rPr>"))


def sz(half_points: int) -> str:
    return f'<w:sz w:val="{half_points}"/><w:szCs w:val="{half_points}"/>'


def restyle(doc) -> None:
    """IEEE's styles at the sizes of the one-column, 11 pt LaTeX paper."""
    styles = doc.styles.element
    lines = '<w:spacing w:before="0" w:after="0" w:line="253" w:lineRule="auto"/>'
    set_style(styles, "BodyText", lines + '<w:ind w:firstLine="218"/><w:jc w:val="both"/>', sz(22))
    set_style(
        styles,
        "Heading1",
        '<w:keepNext/><w:keepLines/><w:numPr><w:numId w:val="4"/></w:numPr>'
        '<w:spacing w:before="320" w:after="80" w:line="253" w:lineRule="auto"/>'
        '<w:ind w:left="0" w:firstLine="0"/><w:jc w:val="center"/><w:outlineLvl w:val="0"/>',
        "<w:smallCaps/>" + sz(22),
    )
    set_style(
        styles,
        "Heading2",
        '<w:keepNext/><w:keepLines/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="4"/></w:numPr>'
        '<w:spacing w:before="300" w:after="60" w:line="253" w:lineRule="auto"/>'
        '<w:ind w:left="0" w:firstLine="0"/><w:jc w:val="left"/><w:outlineLvl w:val="1"/>',
        "<w:i/><w:iCs/>" + sz(22),
    )
    set_style(
        styles,
        "Heading5",
        '<w:keepNext/><w:keepLines/><w:spacing w:before="320" w:after="80" w:line="253" '
        'w:lineRule="auto"/><w:ind w:firstLine="0"/><w:jc w:val="center"/>'
        '<w:outlineLvl w:val="0"/>',
        "<w:smallCaps/>" + sz(22),
    )
    set_style(
        styles,
        "papertitle",
        '<w:spacing w:before="0" w:after="200" w:line="558" w:lineRule="exact"/>'
        '<w:jc w:val="center"/>',
        sz(48),
    )
    set_style(
        styles,
        "Author",
        '<w:spacing w:before="0" w:after="600"/><w:jc w:val="center"/>',
        sz(24),
    )
    set_style(
        styles,
        "Abstract",
        '<w:spacing w:before="0" w:after="0" w:line="250" w:lineRule="auto"/>'
        '<w:ind w:left="438" w:right="438" w:firstLine="328"/><w:jc w:val="both"/>',
        sz(20),
    )
    set_style(
        styles,
        "Keywords",
        '<w:spacing w:before="0" w:after="360" w:line="250" w:lineRule="auto"/>'
        '<w:ind w:left="438" w:right="438" w:firstLine="328"/><w:jc w:val="both"/>',
        sz(20),
        based_on="Abstract",
    )
    set_style(
        styles,
        "figurecaption",
        '<w:numPr><w:numId w:val="2"/></w:numPr><w:spacing w:before="80" w:after="200" '
        'w:line="240" w:lineRule="auto"/><w:ind w:left="0" w:firstLine="0"/><w:jc w:val="both"/>',
        sz(18),
    )
    set_style(
        styles,
        "tablehead",
        '<w:keepNext/><w:numPr><w:numId w:val="9"/></w:numPr><w:spacing w:before="0" w:after="120" '
        'w:line="240" w:lineRule="auto"/><w:ind w:left="0" w:firstLine="0"/><w:jc w:val="center"/>',
        "<w:smallCaps/>" + sz(18),
    )
    cell_spacing = '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
    set_style(styles, "tablecopy", cell_spacing + '<w:jc w:val="left"/>', sz(18))
    set_style(styles, "tablecolhead", cell_spacing + '<w:jc w:val="left"/>', sz(18), based_on="")
    set_style(
        styles,
        "tablefootnote",
        cell_spacing + '<w:jc w:val="both"/>',
        sz(16),
    )
    set_style(
        styles,
        "references",
        '<w:numPr><w:numId w:val="8"/></w:numPr><w:spacing w:before="0" w:after="4" w:line="180" '
        'w:lineRule="exact"/><w:jc w:val="both"/>',
        sz(16),
    )
    set_style(
        styles,
        "equation",
        f'<w:tabs><w:tab w:val="center" w:pos="{TEXT_W // 2}"/>'
        f'<w:tab w:val="right" w:pos="{TEXT_W}"/>'
        '</w:tabs><w:spacing w:before="100" w:after="100" w:line="240" w:lineRule="auto"/>'
        '<w:ind w:firstLine="0"/><w:jc w:val="left"/>',
        sz(22),
    )
    set_style(
        styles,
        "bulletlist",
        '<w:numPr><w:numId w:val="1"/></w:numPr><w:ind w:left="434" w:hanging="216"/>',
        "",
    )
    set_style(
        styles,
        "footnote",
        '<w:numPr><w:numId w:val="0"/></w:numPr>'
        '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        '<w:ind w:firstLine="178"/><w:jc w:val="both"/>',
        sz(18),
    )
    set_style(styles, "Header", f'<w:tabs><w:tab w:val="right" w:pos="{TEXT_W}"/></w:tabs>', sz(16))


def renumber(doc) -> None:
    """The template's lists: heading numbers followed by a space, captions as in IEEEtran."""
    numbering = doc.part.numbering_part.element
    nums = {
        n.get(qn("w:numId")): n.find(qn("w:abstractNumId")).get(qn("w:val"))
        for n in numbering.findall(qn("w:num"))
    }

    def level(num_id: str, ilvl: int):
        abstract = numbering.find(
            f"{{{W_NS}}}abstractNum[@{{{W_NS}}}abstractNumId='{nums[num_id]}']"
        )
        return abstract.find(f"{{{W_NS}}}lvl[@{{{W_NS}}}ilvl='{ilvl}']")

    def setup(num_id, ilvl, text, ind, size, suffix="space", jc="left", tab=None):
        lvl = level(num_id, ilvl)
        lvl.find(qn("w:lvlText")).set(qn("w:val"), text)
        for tag in ("suff", "pPr"):
            old = lvl.find(qn(f"w:{tag}"))
            if old is not None:
                lvl.remove(old)
        lvl.find(qn("w:lvlJc")).set(qn("w:val"), jc)
        lvl.find(qn("w:lvlText")).addprevious(parse_xml(f'<w:suff {NS} w:val="{suffix}"/>'))
        tabs = f'<w:tabs><w:tab w:val="num" w:pos="{tab}"/></w:tabs>' if tab else ""
        lvl.find(qn("w:lvlJc")).addnext(parse_xml(f"<w:pPr {NS}>{tabs}{ind}</w:pPr>"))
        rpr = lvl.find(qn("w:rPr"))
        if rpr is not None:
            for tag in ("sz", "szCs"):
                el = rpr.find(qn(f"w:{tag}"))
                if el is not None:
                    el.set(qn("w:val"), str(size))

    no_ind = '<w:ind w:left="0" w:firstLine="0"/>'
    setup("4", 0, "%1.", no_ind, 22)
    setup("4", 1, "%2.", no_ind, 22)
    setup("2", 0, "Fig. %1.", no_ind, 18)
    setup("9", 0, "TABLE %1", no_ind, 18, suffix="nothing")
    setup("8", 0, "[%1]", '<w:ind w:left="374" w:hanging="374"/>', 16, suffix="tab", tab=374)
    setup("1", 0, "\uf0b7", '<w:ind w:left="434" w:hanging="216"/>', 22, suffix="tab", tab=434)


# ----------------------------------------------------------------------------- the build


class Builder:
    def __init__(self, template: Path, workdir: Path) -> None:
        self.workdir = workdir
        tectonic(MAIN, workdir)
        labels, cites = read_aux(workdir / "main.aux")
        self.bib = read_bbl(workdir / "main.bbl")
        self.latex_pdf = workdir / "main.pdf"
        self.tex = Tex(load_macros(), labels, cites)
        self.omml = Omml(self.tex)
        plain = workdir / "template.docx"
        transitional_copy(template, plain)
        self.doc = Document(str(plain))
        self.body = self.doc.element.body
        self.end = self.body.sectPr
        self.counts = Counter()

    def add(self, xml_or_el):
        el = parse_xml(xml_or_el) if isinstance(xml_or_el, str) else xml_or_el
        self.end.addprevious(el)
        return el

    def runs(self, s: str, base: Run = PLAIN) -> list[Run]:
        return self.tex.runs(self.tex.resolve(s), base)

    # -- the template, emptied

    def clear(self) -> None:
        for child in list(self.body.iterchildren()):
            if child is not self.end:
                self.body.remove(child)
        for rel_id, rel in list(self.doc.part.rels.items()):
            if rel.reltype.endswith(("/image", "/hyperlink", "/customXml", "/footer", "/header")):
                self.doc.part.drop_rel(rel_id)
        for child in list(self.end):
            self.end.remove(child)
        self.end.append(parse_xml(f'<w:pgSz {NS} w:w="{PAGE_W}" w:h="{PAGE_H}"/>'))
        self.end.append(
            parse_xml(
                f'<w:pgMar {NS} w:top="{MARGIN_TOP}" w:right="{MARGIN_LR}" '
                f'w:bottom="{MARGIN_BOTTOM}" '
                f'w:left="{MARGIN_LR}" w:header="{HEADER}" w:footer="{HEADER}" w:gutter="0"/>'
            )
        )
        self.end.append(parse_xml(f'<w:cols {NS} w:space="240"/>'))
        settings = self.doc.settings.element
        for tag in ("embedSystemFonts", "rsids", "attachedTemplate", "docVars"):
            el = settings.find(qn(f"w:{tag}"))
            if el is not None:
                settings.remove(el)

    def header(self, text: str, thanks: list[Run]) -> None:
        """The running head on every page and, as IEEEtran sets \\thanks, the authors'
        affiliation under a short rule at the foot of the first page, without a mark."""
        section = self.doc.sections[0]
        section.different_first_page_header_footer = True
        fields = "".join(
            f"<w:r {NS}>{xml}</w:r>"
            for xml in (
                '<w:fldChar w:fldCharType="begin"/>',
                '<w:instrText xml:space="preserve"> PAGE </w:instrText>',
                '<w:fldChar w:fldCharType="separate"/>',
                "<w:t>1</w:t>",
                '<w:fldChar w:fldCharType="end"/>',
            )
        )
        head = (
            f'<w:p {NS}><w:pPr><w:pStyle w:val="Header"/></w:pPr>'
            f"<w:r><w:rPr><w:caps/></w:rPr><w:t>{esc(text)}</w:t></w:r><w:r><w:tab/></w:r>{fields}</w:p>"
        )
        for part in (section.header, section.first_page_header):
            part.is_linked_to_previous = False
            el = part._element
            for child in list(el):
                el.remove(child)
            el.append(parse_xml(head))
        foot = section.first_page_footer
        foot.is_linked_to_previous = False
        el = foot._element
        for child in list(el):
            el.remove(child)
        el.append(
            parse_xml(
                f'<w:p {NS}><w:pPr><w:pStyle w:val="footnote"/><w:pBdr><w:bottom w:val="single" '
                'w:sz="4" w:space="1" w:color="000000"/></w:pBdr><w:spacing w:after="80"/>'
                f'<w:ind w:left="0" w:right="{TEXT_W * 3 // 4}" w:firstLine="0"/>'
                '<w:rPr><w:sz w:val="4"/></w:rPr></w:pPr></w:p>'
            )
        )
        el.append(parse_xml(para_xml("footnote", thanks)))
        settings = self.doc.settings.element
        if settings.find(qn("w:evenAndOddHeaders")) is not None:
            settings.remove(settings.find(qn("w:evenAndOddHeaders")))

    # -- front matter

    def front(self, main: str) -> tuple[str, list[str], str]:
        title_raw, _ = Tex.group(main, main.index("\\title") + len("\\title"))
        title = self.tex.plain(title_raw.replace("\n", " "))
        author_raw, _ = Tex.group(main, main.index("\\author") + len("\\author"))
        names_raw, _, thanks_raw = author_raw.partition("\\thanks")
        thanks, _ = Tex.group(thanks_raw, 0)
        names = self.tex.plain(names_raw).replace("\u00a0", " ").strip()
        authors = [a.strip() for a in re.split(r",| and ", names) if a.strip()]
        mark_raw, _ = Tex.group(main, main.index("\\markboth") + len("\\markboth"))
        running = self.tex.plain(mark_raw)

        self.add(para_xml("papertitle", [Run(title)]))
        self.thanks = self.runs(re.sub(r"\s+", " ", thanks).strip())
        self.add(para_xml("Author", [Run(names)]))
        heading_ppr = (
            '<w:spacing w:after="100"/><w:ind w:left="0" w:right="0" w:firstLine="0"/>'
            '<w:jc w:val="center"/>'
        )
        self.add(para_xml("Abstract", [Run("Abstract", bold=True)], heading_ppr))
        abstract = strip_comments((HERE / "abstract.tex").read_text(encoding="utf-8"))
        self.add(
            para_xml(
                "Abstract", self.runs(re.sub(r"\s+", " ", abstract)), '<w:spacing w:after="300"/>'
            )
        )
        keywords = strip_comments(find_env(main, "IEEEkeywords")[2])
        self.add(para_xml("Keywords", [Run("Index Terms", bold=True)], heading_ppr))
        self.add(para_xml("Keywords", self.runs(re.sub(r"\s+", " ", keywords).strip())))
        return title, authors, running

    # -- body

    def section_blocks(self, tex: str) -> None:
        """Walk one section file: headings, paragraphs, lists, equations and floats."""
        tex = strip_comments(tex)
        pattern = re.compile(
            r"\\(section\*?|subsection)\{|\\begin\{(figure\*?|table\*?|equation|enumerate|itemize)\}"
            r"|\n[ \t]*\n"
        )
        buffer = ""
        indent = True
        floats: list[tuple[str, str]] = []
        i = 0

        def flush(end_of_paragraph: bool) -> None:
            nonlocal buffer, indent
            text = re.sub(r"\s+", " ", buffer).strip()
            text = re.sub(r"^(\\label\{[^}]*\}\s*)+", "", text)
            if text:
                self.paragraph(text, indent)
            buffer = ""
            if end_of_paragraph:
                indent = True
                for kind, body in floats:
                    self.float(kind, body)
                floats.clear()

        while True:
            m = pattern.search(tex, i)
            if not m:
                buffer += tex[i:]
                flush(True)
                break
            buffer += tex[i : m.start()]
            if m.group(1):
                flush(True)
                head, j = Tex.group(tex, m.end() - 1)
                self.heading(m.group(1), head)
                i = j
                indent = True
                continue
            if m.group(2):
                env = m.group(2)
                _, end, body = find_env(tex, env, m.start())
                if env in ("figure", "figure*", "table", "table*"):
                    floats.append((env, body))
                elif env == "equation":
                    flush(False)
                    self.equation(body)
                    indent = False
                else:
                    flush(False)
                    self.listing(env, body)
                    indent = False
                i = end
                after = tex[i:]
                if env.startswith(("equation", "enumerate", "itemize")) and re.match(
                    r"[ \t]*\n[ \t]*\n", after
                ):
                    indent = True
                continue
            if buffer.strip():
                flush(True)
            else:
                flush(True)
            i = m.end()

    def heading(self, kind: str, head: str) -> None:
        text = self.tex.plain(head)
        if kind == "section":
            style = "Heading1"
        elif kind == "subsection":
            style = "Heading2"
        else:
            style = "Heading5"
        self.add(para_xml(style, [Run(text)]))
        self.counts[style] += 1

    def paragraph(self, text: str, indent: bool) -> None:
        ppr = "" if indent else '<w:ind w:firstLine="0"/>'
        m = re.match(r"\\IEEEPARstart\{(\w)\}\{(\w*)\}", text)
        if m:
            drop = (
                f'<w:p {NS}><w:pPr><w:pStyle w:val="BodyText"/><w:keepNext/>'
                '<w:framePr w:dropCap="drop" w:lines="2" w:wrap="around" w:vAnchor="text" '
                'w:hAnchor="text"/><w:spacing w:line="507" w:lineRule="exact"/>'
                '<w:ind w:firstLine="0"/><w:textAlignment w:val="baseline"/></w:pPr>'
                '<w:r><w:rPr><w:position w:val="-3"/><w:sz w:val="62"/><w:szCs w:val="62"/></w:rPr>'
                f"<w:t>{m.group(1)}</w:t></w:r></w:p>"
            )
            self.add(drop)
            text = m.group(2) + text[m.end() :]
            ppr = '<w:ind w:firstLine="0"/>'
        align = ""
        if text.startswith("{\\raggedright"):
            text = text[len("{\\raggedright") :].strip()
            text = re.sub(r"\\par\}$", "", text).strip()
            align = '<w:jc w:val="left"/>'
        self.add(para_xml("BodyText", self.runs(text), ppr + align))
        self.counts["paragraphs"] += 1

    def listing(self, env: str, body: str) -> None:
        items = re.split(r"\\item", body)[1:]
        for item in items:
            item = re.sub(r"\s+", " ", item).strip()
            if env == "enumerate":
                label, j = Tex.optional(item, 0)
                runs = [Run(label + "\t"), *self.runs(item[j:].strip())]
                self.add(
                    para_xml(
                        "BodyText",
                        runs,
                        '<w:tabs><w:tab w:val="left" w:pos="434"/></w:tabs>'
                        '<w:ind w:left="434" w:hanging="434"/>',
                    )
                )
            else:
                self.add(para_xml("bulletlist", self.runs(item)))
            self.counts["list items"] += 1

    def equation(self, body: str) -> None:
        label = re.search(r"\\label\{([^}]+)\}", body)
        number = self.tex.labels[label.group(1)]
        latex = re.sub(r"\\label\{[^}]+\}", "", body).strip()
        # A wide gap is text between two equation objects, so every editor keeps it.
        parts = [f"<m:oMath>{self.omml.convert(part)}</m:oMath>" for part in latex.split("\\qquad")]
        gap = '<w:r><w:t xml:space="preserve">\u2003\u2003</w:t></w:r>'
        self.add(
            f'<w:p {NS}><w:pPr><w:pStyle w:val="equation"/></w:pPr><w:r><w:tab/></w:r>'
            f"{gap.join(parts)}<w:r><w:tab/><w:t>({number})</w:t></w:r></w:p>"
        )
        self.counts["equations"] += 1

    # -- floats

    def float(self, env: str, body: str) -> None:
        if env.startswith("figure"):
            self.figure_float(body)
        else:
            self.table(body)

    def figure_float(self, body: str) -> None:
        boxes = []
        pos = 0
        while True:
            m = re.compile(r"\\begin\{minipage\}\[t\]\{([^}]*)\}").search(body, pos)
            if not m:
                break
            end = body.index("\\end{minipage}", m.end())
            boxes.append((m.group(1), body[m.end() : end]))
            pos = end + len("\\end{minipage}")
        if not boxes:
            boxes = [("\\textwidth", body)]
        figs = [self.figures[self.figure_label(content)] for _, content in boxes]
        if len(figs) == 1:
            fig = figs[0]
            self.add(
                para_xml(
                    "Normal",
                    "",
                    '<w:keepNext/><w:spacing w:before="60" w:after="0"/><w:jc w:val="center"/>',
                )
            )
            self.picture(self.end.getprevious(), fig)
            self.add(self.caption_xml(fig))
            return
        widths = [self.length(w) for w, _ in boxes]
        gap = TEXT_W - sum(widths)
        grid = [widths[0], gap, widths[1]]
        cells = []
        for n, fig in enumerate(figs):
            pic = para_xml(
                "Normal",
                "",
                '<w:keepNext/><w:spacing w:before="60" w:after="0"/><w:jc w:val="center"/>',
            )
            cells.append((pic, self.caption_xml(fig), grid[2 * n]))
        tbl = parse_xml(self.grid_table(cells, gap))
        self.add(tbl)
        pics = [
            p
            for p in tbl.iter(qn("w:p"))
            if p.find(qn("w:pPr") + "/" + qn("w:keepNext")) is not None
        ]
        for p, fig in zip(pics, figs, strict=True):
            self.picture(p, fig)

    def grid_table(self, cells, gap: int) -> str:
        none = "".join(
            f'<w:{side} w:val="nil"/>'
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in (cells[0][2], gap, cells[1][2]))
        tcs = []
        for n, (pic, cap, width) in enumerate(cells):
            tcs.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>{pic}{cap}</w:tc>'
            )
            if n == 0:
                tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="{gap}" w:type="dxa"/></w:tcPr><w:p/></w:tc>')
        return (
            f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{TEXT_W}" w:type="dxa"/><w:jc w:val="center"/>'
            f'<w:tblBorders>{none}</w:tblBorders><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
            '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="0000"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr>{''.join(tcs)}</w:tr></w:tbl>"
        )

    def figure_label(self, content: str) -> str:
        return re.search(r"\\label\{([^}]+)\}", content).group(1)

    def picture(self, p, fig: Fig) -> None:
        run = Paragraph(p, self.doc._body).add_run()
        run.add_picture(io.BytesIO(fig.png), width=Emu(round(fig.width_pt * 12700)))
        docpr = p.find(
            ".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
        )
        docpr.set("name", f"Figure {self.tex.labels[fig.label]}")
        docpr.set("descr", self.tex.plain(fig.caption.split(". ")[0]) + ".")
        self.counts["figures"] += 1

    def caption_xml(self, fig: Fig) -> str:
        return para_xml("figurecaption", self.runs(re.sub(r"\s+", " ", fig.caption)))

    @staticmethod
    def length(expr: str) -> int:
        m = re.fullmatch(r"([\d.]*)\\(textwidth|linewidth)", expr.strip())
        if not m:
            raise BuildError(f"unknown width {expr}")
        return round(float(m.group(1) or 1) * TEXT_W)

    def collect_figures(self, sources: list[str]) -> list[Fig]:
        figs: list[Fig] = []
        for tex in sources:
            tex = strip_comments(tex)
            for env in ("figure", "figure*"):
                pos = 0
                while (found := find_env(tex, env, pos)) is not None:
                    _, pos, body = found
                    boxes = re.findall(
                        r"\\begin\{minipage\}\[t\]\{([^}]*)\}(.*?)\\end\{minipage\}", body, re.S
                    ) or [("\\textwidth", body)]
                    for width, content in boxes:
                        cap, _ = Tex.group(content, content.index("\\caption") + len("\\caption"))
                        label = self.figure_label(content)
                        start = content.index("\\caption")
                        _, cap_end = Tex.group(content, start + len("\\caption"))
                        drawing = content[:start] + content[cap_end:]
                        drawing = re.sub(
                            r"\\label\{[^}]*\}|\\vspace\{[^}]*\}|\\centering", "", drawing
                        )
                        figs.append(Fig(label, width, drawing.strip(), cap))
        figs.sort(key=lambda f: int(self.tex.labels[f.label]))
        numbers = [int(self.tex.labels[f.label]) for f in figs]
        if numbers != list(range(1, len(figs) + 1)):
            raise BuildError(f"figure numbers out of order: {numbers}")
        return figs

    # -- tables

    def table(self, body: str) -> None:
        cap, _ = Tex.group(body, body.index("\\caption") + len("\\caption"))
        label = re.search(r"\\label\{([^}]+)\}", body).group(1)
        sep = re.search(r"\\setlength\{\\tabcolsep\}\{([\d.]+)pt\}", body)
        colsep = round(float(sep.group(1)) * 20) if sep else 120
        m = re.search(r"\\begin\{(tabularx|tabular)\}", body)
        kind = m.group(1)
        i = m.end()
        if kind == "tabularx":
            _, i = Tex.group(body, i)
        spec, i = Tex.group(body, i)
        rows_tex = body[i : body.index(f"\\end{{{kind}}}")]
        cols = self.column_spec(spec)

        rows: list[dict] = []
        rule_next = "top"
        for raw in re.split(r"\\\\", rows_tex):
            raw = raw.strip()
            rules = re.findall(r"\\(toprule|midrule|bottomrule)", raw)
            raw = re.sub(r"\\(toprule|midrule|bottomrule)", "", raw).strip()
            for rule in rules:
                if rule == "bottomrule" and rows:
                    rows[-1]["bottom"] = True
                elif rule == "midrule" and rows:
                    rows[-1]["bottom_thin"] = True
            if not raw:
                continue
            if raw.startswith("\\multicolumn"):
                n, j = Tex.group(raw, len("\\multicolumn"))
                _, j = Tex.group(raw, j)
                content, _ = Tex.group(raw, j)
                rows.append({"span": int(n), "cells": [content], "top": rule_next == "top"})
            else:
                cells = [c.strip() for c in re.split(r"(?<!\\)&", raw)]
                if len(cells) != len(cols):
                    raise BuildError(f"{label}: row with {len(cells)} cells, {len(cols)} columns")
                rows.append({"span": 1, "cells": cells, "top": rule_next == "top"})
            rule_next = ""

        widths = self.column_widths(kind, cols, rows, colsep)
        number = self.tex.labels[label]
        caption = [Run("\n"), *self.runs(re.sub(r"\s+", " ", cap))]
        cap_xml = "<w:r><w:br/></w:r>" + "".join(run_xml(r) for r in caption[1:])
        self.add(para_xml("tablehead", cap_xml))

        heavy = '<w:{side} w:val="single" w:sz="7" w:space="0" w:color="000000"/>'
        light = '<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        trs = []
        for n, row in enumerate(rows):
            borders = ""
            if row.get("top"):
                borders += heavy.format(side="top")
            if row.get("bottom"):
                borders += heavy.format(side="bottom")
            elif row.get("bottom_thin"):
                borders += light.format(side="bottom")
            header = n == 0
            tcs = []
            if row["span"] > 1:
                runs = self.runs(row["cells"][0])
                runs = self.cell_runs(row["cells"][0])
                tcs.append(
                    self.cell(
                        runs,
                        sum(widths[: row["span"]]),
                        cols[0],
                        borders,
                        header,
                        row["span"],
                        first=True,
                        last=True,
                    )
                )
            else:
                for k, (text, width, align) in enumerate(
                    zip(row["cells"], widths, cols, strict=True)
                ):
                    tcs.append(
                        self.cell(
                            self.cell_runs(text),
                            width,
                            align,
                            borders,
                            header,
                            1,
                            k == 0,
                            k == len(cols) - 1,
                        )
                    )
            trpr = "<w:tblHeader/>" if header else ""
            row_xml = "".join(tcs)
            if n < len(rows) - 1:
                row_xml = row_xml.replace("<w:pPr>", "<w:pPr><w:keepNext/>")
            trs.append(f"<w:tr><w:trPr><w:cantSplit/>{trpr}</w:trPr>{row_xml}</w:tr>")
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        total = sum(widths)
        self.add(
            f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/><w:jc w:val="center"/>'
            '<w:tblLayout w:type="fixed"/>'
            f'<w:tblCellMar><w:top w:w="10" w:type="dxa"/><w:left w:w="{colsep}" w:type="dxa"/>'
            f'<w:bottom w:w="10" w:type="dxa"/><w:right w:w="{colsep}" w:type="dxa"/>'
            "</w:tblCellMar>"
            '<w:tblLook w:val="0000"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(trs)}</w:tbl>"
        )
        self.add(
            para_xml(
                "BodyText",
                [],
                '<w:spacing w:before="0" w:after="0" w:line="120" w:lineRule="exact"/>',
            )
        )
        self.counts["tables"] += 1
        if str(self.counts["tables"]) != str(roman_to_int(number)):
            raise BuildError(f"table {label} is number {number} in LaTeX")

    def cell_runs(self, text: str) -> list[Run]:
        size = 0
        if text.startswith("\\scriptsize"):
            size = 16
        runs = self.runs(text)
        if size:
            runs = [replace(r, size=r.size or size) for r in runs]
        return runs

    def cell(self, runs, width, align, borders, header, span, first, last) -> str:
        jc = {"l": "left", "c": "center", "r": "right", "L": "left", "X": "both"}[
            align[0] if align[0] != "p" else "l"
        ]
        mar = ""
        if first:
            mar += '<w:left w:w="0" w:type="dxa"/>'
        if last:
            mar += '<w:right w:w="0" w:type="dxa"/>'
        tcpr = f'<w:tcW w:w="{width}" w:type="dxa"/>'
        if span > 1:
            tcpr += f'<w:gridSpan w:val="{span}"/>'
        if borders:
            tcpr += f"<w:tcBorders>{borders}</w:tcBorders>"
        if mar:
            tcpr += f"<w:tcMar>{mar}</w:tcMar>"
        style = "tablecolhead" if header else "tablecopy"
        return (
            f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{para_xml(style, runs, f'<w:jc w:val="{jc}"/>')}</w:tc>"
        )

    @staticmethod
    def column_spec(spec: str) -> list[str]:
        cols = []
        i = 0
        while i < len(spec):
            c = spec[i]
            if c in "@>":
                _, i = Tex.group(spec, i + 1)
                continue
            if c == "p":
                width, i = Tex.group(spec, i + 1)
                cols.append(f"p{width}")
                continue
            if c in "lcrLX":
                cols.append(c)
            i += 1
        return cols

    def column_widths(self, kind: str, cols: list[str], rows: list[dict], colsep: int) -> list[int]:
        """Twips per column: p{} as given, l/c/r as wide as their longest cell, and X or L
        sharing what is left of the text width, as tabularx does."""
        natural = [0.0] * len(cols)
        for row in rows:
            if row["span"] > 1:
                continue
            for k, text in enumerate(row["cells"]):
                runs = self.cell_runs(text)
                width = 0.0
                for r in runs:
                    size = (r.size or 18) / 2
                    if r.vert:
                        size *= 0.65
                    width += text_width(r.text, r.italic, r.bold, size)
                natural[k] = max(natural[k], width)
        widths: list[int | None] = []
        for k, col in enumerate(cols):
            pad = colsep * ((k > 0) + (k < len(cols) - 1))
            if col.startswith("p"):
                cm = float(re.fullmatch(r"([\d.]+)cm", col[1:]).group(1))
                widths.append(round(cm / 2.54 * 72 * 20) + pad)
            elif col in "lcr":
                widths.append(round(natural[k] * 20 * 1.02) + 30 + pad)
            else:
                widths.append(None)
        flexible = [k for k, w in enumerate(widths) if w is None]
        if kind == "tabularx":
            rest = TEXT_W - sum(w for w in widths if w is not None)
            for k in flexible:
                pad = colsep * ((k > 0) + (k < len(cols) - 1))
                widths[k] = rest // len(flexible)
        elif flexible:
            raise BuildError("X column in a plain tabular")
        total = sum(widths)
        if total > TEXT_W:
            raise BuildError(f"table wider than the text: {total} > {TEXT_W}")
        return [int(w) for w in widths]

    # -- references

    def references(self) -> None:
        cites = self.tex.cites
        order = [key for key, _ in self.bib]
        if [cites[k] for k in order] != list(range(1, len(order) + 1)):
            raise BuildError("the .bbl and the .aux disagree on the reference order")
        for _, body in self.bib:
            runs = self.tex.runs(accent_fix(body))
            self.add(para_xml("references", runs))
            self.counts["references"] += 1

    # -- metadata

    def properties(self, title: str, authors: list[str]) -> None:
        cp = self.doc.core_properties
        cp.title = title
        cp.author = ", ".join(authors)
        for field in (
            "subject",
            "keywords",
            "comments",
            "category",
            "content_status",
            "identifier",
            "language",
            "version",
            "last_modified_by",
        ):
            setattr(cp, field, "")
        cp.revision = 1
        now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
        cp.created = now
        cp.modified = now

    # -- the whole paper

    def build(self, out: Path) -> dict:
        main = strip_comments(MAIN.read_text(encoding="utf-8"))
        sources = [(HERE / f"{name}.tex").read_text(encoding="utf-8") for name in SECTIONS]
        figs = self.collect_figures(sources)
        self.figure_pdf = render_figures(figs, self.workdir, self.workdir / "main.aux")
        self.figures = {f.label: f for f in figs}

        self.clear()
        renumber(self.doc)
        restyle(self.doc)
        title, authors, running = self.front(main)
        self.header(running, self.thanks)
        for tex in sources:
            self.section_blocks(tex)
        closing = main[main.index("\\section*{Acknowledgment}") : main.index("\\bibliographystyle")]
        self.section_blocks(closing)

        # The main text ends one section; the references run in two columns after it.
        last = self.end.getprevious()
        main_sect = copy.deepcopy(self.end)
        ppr = last.find(qn("w:pPr"))
        ppr.append(main_sect)
        for tag in ("headerReference", "footerReference", "titlePg"):
            for ref in self.end.findall(qn(f"w:{tag}")):
                self.end.remove(ref)
        self.end.find(qn("w:pgSz")).addprevious(parse_xml(f'<w:type {NS} w:val="continuous"/>'))
        cols = self.end.find(qn("w:cols"))
        cols.set(qn("w:num"), "2")
        cols.set(qn("w:space"), "240")
        self.add(para_xml("Heading5", [Run("References")]))
        self.references()

        self.properties(title, authors)
        self.doc.save(str(out))
        scrub(out)
        unused = [f for f in self.figures if f not in {fig.label for fig in figs}]
        if unused:
            raise BuildError(f"figures never placed: {unused}")
        if self.counts["figures"] != len(figs):
            raise BuildError(f"{self.counts['figures']} of {len(figs)} figures placed")
        return dict(self.counts) | {"macros used": len(self.tex.used_macros)}


def roman_to_int(s: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for a, b in zip(s, s[1:] + " ", strict=True):
        v = values[a]
        total += -v if b != " " and values.get(b, 0) > v else v
    return total


APP_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    "<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
    "<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>"
    "<HyperlinksChanged>false</HyperlinksChanged></Properties>"
)


def scrub(path: Path) -> None:
    """Drop the template's statistics and its empty bibliography store."""
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename.startswith("customXml/"):
                continue
            data = src.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = APP_XML.encode()
            elif item.filename == "[Content_Types].xml":
                data = re.sub(rb'<Override PartName="/customXml/[^>]*/>', b"", data)
            dst.writestr(item, data)
    tmp.replace(path)


def to_pdf(docx: Path, pdf: Path) -> None:
    """LibreOffice, with Times New Roman and Courier New given to a fresh profile: run
    headless it does not see the Mac's own fonts."""
    with tempfile.TemporaryDirectory() as tmp:
        fonts = Path(tmp) / "profile" / "user" / "fonts"
        fonts.mkdir(parents=True)
        for pattern in PROFILE_FONTS:
            for f in FONT_DIR.glob(pattern):
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


# ----------------------------------------------------------------------------- the text check


def words_of(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z0-9]+", text)


def roman(n: int) -> str:
    out = ""
    for value, letters in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out += letters
            n -= value
    return out


def docx_paragraphs(path: Path) -> list[str]:
    """Paragraphs of the Word file with the numbers Word adds to them, and each table row as
    one line, read in document order."""
    doc = Document(str(path))
    t_tags = (qn("w:t"), f"{{{M_NS}}}t")
    counts = Counter()
    texts = []

    def text_of(el) -> str:
        return "".join(t.text or "" for t in el.iter(*t_tags))

    def label(p) -> str:
        style = p.find(qn("w:pPr") + "/" + qn("w:pStyle"))
        style = style.get(qn("w:val")) if style is not None else ""
        counts[style] += 1
        if style == "Heading1":
            counts["Heading2"] = 0
            return roman(counts[style]) + ". "
        if style == "Heading2":
            return "ABCDEFGHIJ"[counts[style] - 1] + ". "
        if style == "figurecaption":
            return f"Fig. {counts[style]}. "
        if style == "tablehead":
            return f"TABLE {roman(counts[style])} "
        if style == "references":
            return f"[{counts[style]}] "
        return ""

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            texts.append(label(child) + text_of(child))
        elif child.tag == qn("w:tbl"):
            for tr in child.iter(qn("w:tr")):
                cells = []
                for p in tr.iter(qn("w:p")):
                    cells.append(label(p) + text_of(p))
                texts.append(" ".join(c for c in cells if c.strip()))
    texts += [text_of(p) for p in doc.sections[0].first_page_footer._element.iter(qn("w:p"))]
    return [t for t in texts if t.strip()]


def pdf_paragraphs(pdf: Path, figure_pdf: fitz.Document | None) -> list[str]:
    """Text blocks of the LaTeX PDF, without running heads and the text inside figures."""
    figure_lines = set()
    if figure_pdf is not None:
        for page in figure_pdf:
            for line in page.get_text().splitlines():
                figure_lines.add(" ".join(words_of(line)))
    blocks = []
    for page in fitz.open(pdf):
        for block in page.get_text("blocks"):
            y1, text = block[3], block[4]
            if y1 < 40:
                continue
            lines = [ln for ln in text.splitlines() if " ".join(words_of(ln)) not in figure_lines]
            if lines:
                blocks.append(lines)
    return ["\n".join(b) for b in blocks]


def dehyphenate(text: str, vocabulary: set[str]) -> str:
    def join(m: re.Match) -> str:
        whole = (m.group(1) + m.group(2)).lower()
        return m.group(1) + m.group(2) if whole in vocabulary else m.group(1) + "-" + m.group(2)

    text = re.sub(r"(\w+)-\n(\w+)", join, unicodedata.normalize("NFKC", text))
    return text.replace("\n", " ")


def grams(words: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


def check(docx: Path, pdf: Path, figure_pdf: fitz.Document | None, n: int = 8) -> bool:
    """Every block of the LaTeX PDF in the Word file and the other way round, by runs of n
    words, and no run more often in Word than in the PDF."""
    ours_paras = docx_paragraphs(docx)
    ours_words = [w for p in ours_paras for w in words_of(p)]
    theirs_paras = [dehyphenate(b, set(ours_words)) for b in pdf_paragraphs(pdf, figure_pdf)]
    theirs_words = [w for p in theirs_paras for w in words_of(p)]
    ours, theirs = Counter(grams(ours_words, n)), Counter(grams(theirs_words, n))
    print(f"{n}-word runs: Word {sum(ours.values())}, LaTeX PDF {sum(theirs.values())}")
    print(f"  PDF runs found in Word: {sum(1 for g in theirs if g in ours) / len(theirs):.2%}")
    print(f"  Word runs found in the PDF: {sum(1 for g in ours if g in theirs) / len(ours):.2%}")
    extra = [g for g, c in ours.items() if c > theirs.get(g, 0) and g in theirs]
    print(f"  runs more often in Word than in the PDF: {len(extra)}")
    for g in extra[:10]:
        print("   ", " ".join(g))
    short = 0
    for where, paras, other in (
        ("PDF block", theirs_paras, ours),
        ("Word paragraph", ours_paras, theirs),
    ):
        for para in paras:
            words = words_of(para)
            if len(words) < n:
                continue
            share = sum(1 for g in grams(words, n) if g in other) / (len(words) - n + 1)
            if share < 0.9:
                short += 1
                print(f"  {where} covered {share:.0%}: {para[:150]!r}")
    print(f"  blocks or paragraphs below 90 %: {short}")
    # Tables come out of the PDF column by column, so their cells are checked one by one.
    stream = " " + " ".join(theirs_words) + " "
    cells = lost = 0
    for tc in Document(str(docx)).element.body.iter(qn("w:tc")):
        words = words_of("".join(t.text or "" for t in tc.iter(qn("w:t"))))
        if not words:
            continue
        cells += 1
        if f" {' '.join(words)} " not in stream:
            lost += 1
            print(f"  table cell not in the PDF: {' '.join(words)[:100]!r}")
    print(f"  table and figure cells: {cells}, not found in the PDF: {lost}")
    return not extra and not lost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--pdf", action="store_true", help="also convert with LibreOffice")
    parser.add_argument("--check", action="store_true", help="8-word check against the LaTeX PDF")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        try:
            template = fetch_template(args.template, workdir)
            builder = Builder(template, workdir)
            info = builder.build(OUT_DOCX)
        except BuildError as err:
            print(f"build failed: {err}", file=sys.stderr)
            return 1
        print(f"wrote {OUT_DOCX.relative_to(ROOT)}: {info}")
        if OUT_DOCX.stat().st_size > 5_000_000:
            print(f"{OUT_DOCX.name} is over 5 MB", file=sys.stderr)
            return 1
        if args.pdf:
            to_pdf(OUT_DOCX, OUT_PDF)
            print(f"wrote {OUT_PDF.relative_to(ROOT)} ({len(fitz.open(OUT_PDF))} pages)")
        if args.check:
            reference = REFERENCE_PDF if REFERENCE_PDF.exists() else builder.latex_pdf
            if not check(OUT_DOCX, reference, builder.figure_pdf):
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
