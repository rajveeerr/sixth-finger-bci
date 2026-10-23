"""Build the final presentation, report/slides/sixth-finger-bci.pptx.

uv run --with python-pptx==1.0.2 python report/slides/build_slides.py
uv run --with python-pptx==1.0.2 python report/slides/build_slides.py --pdf

A number on a slide is written as {macroName} (or {macroName:fmt}) and filled from
paper/generated/numbers.tex, so the deck cannot drift from the paper and the report; the
speaker notes name every macro with its results file. The figures are the page's own
(docs/figures/web/), and their printed values are checked against the same macros through the
page's data.json. The colours are read from web/src/styles.css. The build fails on text under
18 pt, text that does not fit its box, a figure whose smallest text would print under 18 pt, a
digit typed by hand, or a talk that does not come to 15 minutes.
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "sixth-finger-bci.pptx"
OUTLINE = HERE / "outline.md"
NUMBERS = ROOT / "paper" / "generated" / "numbers.tex"
INDEX = ROOT / "paper" / "generated" / "numbers-index.md"
STYLES = ROOT / "web" / "src" / "styles.css"
PAGE_DATA = ROOT / "web" / "src" / "explain" / "data.json"
FIGURES = ROOT / "docs" / "figures"

# The slide in points (16:9) and the frame every content slide shares.
W, H = 960.0, 540.0
LEFT, RIGHT = 44.0, 916.0
BODY_W = RIGHT - LEFT
HEAD_Y, HEAD_H = 52.0, 76.0
BODY_Y, BODY_B = 136.0, 528.0
BODY_H = BODY_B - BODY_Y
MIN_PT = 18.0
HEAD_PT = 28.0
TALK_SECONDS = 15 * 60
DEMO_SECONDS = 3 * 60
MAX_BYTES = 5_000_000
FONT = "Inter"
SERIF = "Georgia"
AUTHORS = "Rajveer Singh, Vivek Yadav, Ansh Dahiya"
SITE = "sixthfinger.rajveers.com"
# Fixed so that an unchanged deck is the same file byte for byte.
STAMP = (2026, 10, 23, 0, 0, 0)

# Numbers said in the notes that are settings or the study's design, not results, with where
# each is fixed.
WINDOW = (
    "Setting, not a result: each reading is 4 s of signal (configs/data.yaml, window 1.0 to 5.0 s "
    "after the cue)."
)
REPLAY = (
    "Settings, not results: a 4 s window every 0.5 s; the gate switches on when the smoothed "
    "chance of a movement is above 0.6 twice in a row and off below 0.45 "
    "(configs/experiments/ex5_live_switch.yaml, gate)."
)
DESIGN = (
    "The study's design, not a result (docs/dataset-card.md, from Wang et al., 2026): sessions "
    "before two weeks of therapy, after it and a month later; 4 runs of 20 trials a session; a "
    "trial is rest, get ready, then imagine for 6 s."
)

DASHES = {"dash": MSO_LINE_DASH_STYLE.DASH, "dot": MSO_LINE_DASH_STYLE.ROUND_DOT}
PLACEHOLDER = re.compile(r"\{([A-Za-z]+)(?::([a-z0-9]+))?\}")
# Digits a slide may carry without a macro: years in a citation, the names of runs, sessions
# and hypotheses, the licence, the site's address.
FREE_DIGITS = re.compile(
    r"\b(?:19|20)\d\d\b|\bruns? \d(?: and \d)?\b|\bSession \d\b|\bpatients? \d+(?: and \d+)?\b"
    r"|\bH\d[ab]?\b|\b95% interval|CC BY 4\.0|BNCI 2014-001|Cho 2017",
    re.IGNORECASE,
)

# Inter's advance widths (per 1000 em) for the overflow check, from the page's own font file.
_CHARS = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~−×’“”–—·…é"
)
_REGULAR = [
    281, 288, 466, 633, 642, 982, 644, 300, 365, 365, 501, 662, 288, 460, 288, 360, 631, 407,
    610, 618, 646, 593, 620, 566, 619, 620, 288, 302, 662, 662, 662, 511, 966, 690, 654, 730,
    722, 601, 590, 746, 743, 269, 571, 672, 565, 903, 753, 765, 639, 765, 644, 642, 646, 744,
    690, 985, 682, 679, 629, 365, 360, 365, 471, 456, 323, 562, 612, 571, 612, 583, 370, 613,
    591, 242, 242, 549, 242, 876, 591, 600, 612, 612, 376, 528, 327, 591, 562, 818, 546, 562,
    552, 426, 333, 426, 662, 662, 662, 261, 440, 440, 500, 1000, 288, 864, 583,
]  # fmt: skip
_BOLD = [
    237, 338, 551, 649, 655, 1016, 672, 339, 377, 377, 559, 679, 334, 468, 334, 388, 674, 431,
    629, 646, 676, 622, 649, 582, 651, 649, 334, 343, 679, 679, 679, 560, 1016, 747, 662, 740,
    722, 607, 587, 750, 747, 281, 584, 719, 565, 932, 762, 771, 648, 777, 657, 655, 667, 732,
    747, 1038, 738, 731, 664, 377, 388, 377, 487, 476, 365, 581, 630, 588, 630, 596, 398, 632,
    623, 271, 271, 580, 271, 913, 623, 613, 630, 630, 407, 560, 366, 623, 600, 850, 580, 602,
    573, 469, 372, 469, 679, 679, 679, 311, 540, 532, 500, 1000, 334, 1002, 596,
]  # fmt: skip
WIDTHS = {
    False: dict(zip(_CHARS, _REGULAR, strict=True)),
    True: dict(zip(_CHARS, _BOLD, strict=True)),
}
# PowerPoint's single line spacing for Inter: (ascender + descender) / em.
LINE = (1984 + 494) / 2048

C: dict[str, RGBColor] = {}


def load_colours() -> None:
    """The page's palette, from the :root block of its stylesheet."""
    css = STYLES.read_text()
    start = css.index(":root")
    block = css[start : css.index("}", start)]
    found = dict(re.findall(r"--([a-z0-9-]+):\s*#([0-9a-fA-F]{6})", block))
    for key in ["page", "ink", "ink-2", "ink-3", "ink-4", "rule", "chip", "rest", "hand", "sixth"]:
        C[key] = RGBColor.from_string(found[key].upper())
    C["white"] = RGBColor(0xFF, 0xFF, 0xFF)


# Numbers


@dataclass(frozen=True)
class Macro:
    name: str
    raw: str
    meaning: str
    source: str


def load_macros() -> dict[str, Macro]:
    """Every macro of numbers.tex with its meaning and results file from the index."""
    info: dict[str, tuple[str, str]] = {}
    source, last_full = "", ""
    for line in INDEX.read_text().splitlines():
        head = re.fullmatch(r"`([a-z0-9_/.\-]+\.(?:csv|json|md))`", line.strip())
        if head:
            source, last_full = "results/" + head.group(1), ""
            continue
        row = re.match(r"\| `\\([A-Za-z]+)` \| [^|]* \| ([^|]*) \|", line)
        if row:
            meaning = row.group(2).strip()
            if "," in meaning or ":" in meaning:
                last_full = meaning
            elif last_full:
                meaning = f"{meaning} [{last_full}]"
            info[row.group(1)] = (meaning, source)
    macros = {}
    for line in NUMBERS.read_text().splitlines():
        m = re.fullmatch(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", line.strip())
        if m and m.group(1) in info:
            meaning, src = info[m.group(1)]
            macros[m.group(1)] = Macro(m.group(1), m.group(2), meaning, src)
    return macros


@dataclass
class Span:
    text: str
    bold: bool | None = None
    italic: bool = False
    serif: bool = False
    color: str | None = None
    size: float | None = None
    sup: bool = False
    macro: str | None = None
    # Axis ticks and ordinals: digits that are a scale or a label, not a result.
    free: bool = False


def _parse(raw: str) -> tuple[Decimal | None, int | None, str]:
    s = raw
    inner = re.fullmatch(r"\\ensuremath\{(.*)\}", s)
    if inner:
        s = inner.group(1)
    sci = re.fullmatch(r"(-?[\d.]+)\\times10\^\{(-?\d+)\}", s)
    if sci:
        return Decimal(sci.group(1)), int(sci.group(2)), ""
    plain = s.replace("\\,", "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", plain):
        return Decimal(plain), None, ""
    return None, None, s.replace("\\_", "_")


def _round(d: Decimal, places: int, name: str) -> Decimal:
    step = Decimal(1).scaleb(-places)
    rest = abs(d - d.quantize(step, rounding=ROUND_DOWN))
    if rest == step / 2:
        raise ValueError(f"\\{name} = {d} could round either way to {places} places")
    return d.quantize(step, rounding=ROUND_HALF_UP)


def _decimal_text(d: Decimal, thousands: bool) -> str:
    # As the macro writes it (60.0 stays 60.0), so a slide reads exactly like the paper.
    return format(d, ",f" if thousands else "f").replace("-", "−")


def show(m: Macro, fmt: str) -> list[Span]:
    """A macro as slide text: as written, or rounded where the format asks and it is safe."""
    value, exp, text = _parse(m.raw)
    if value is None:
        return [Span(text, macro=m.name)]
    if exp is not None:
        mantissa = _decimal_text(value, False)
        return [
            Span(f"{mantissa} × 10", macro=m.name),
            Span(str(exp).replace("-", "−"), sup=True, macro=m.name),
        ]
    if fmt == "int":
        value = _round(value, 0, m.name)
    elif fmt == "1":
        value = _round(value, 1, m.name)
    elif fmt == "sec":
        value = _round(value * 60, 0, m.name)
    elif fmt == "abs":
        value = abs(value)
    elif fmt:
        raise ValueError(f"unknown format {fmt} for \\{m.name}")
    return [Span(_decimal_text(value, "\\," in m.raw), macro=m.name)]


def value_of(m: Macro) -> Decimal:
    value, _, _ = _parse(m.raw)
    if value is None:
        raise ValueError(f"\\{m.name} is not a number")
    return value


# Figures


@dataclass(frozen=True)
class Fig:
    file: str
    shows: str
    crop: tuple[int, int, int, int] | None = None
    px_per_css: int = 3
    # The smallest text left in the crop, in CSS px (from the figure's SVG or the page's
    # stylesheet); None when the crop holds no text but the lettering drawn on objects.
    small: float | None = None
    # (macro, path in data.json, factor): the figure prints the data.json value.
    checks: tuple[tuple[str, str, int], ...] = ()


_LEAK = (
    ("rqOneCspLdaPaperReplicaMean", "leak.mean_replica", 100),
    ("rqOneCspLdaCvLeakfreeMean", "leak.mean_leakfree", 100),
)
_PUBLISHED = (
    ("rqOnePublishedGroupBCspLda", "leak.published.0", 100),
    ("rqOnePublishedGroupTCspLda", "leak.published.1", 100),
)
_CURVE = tuple(
    (f"rqTwoRestAhSf{method}K{k}Mean", f"calibration.{key}.{i}.mean", 100)
    for method, key in (("RctTslr", "transfer"), ("TsLr", "scratch"))
    for i, k in enumerate(["One", "Two", "Three", "Five", "Ten", "All"])
) + tuple(
    (f"rqTwoMinutesK{k}", f"calibration.transfer.{i}.minutes", 1)
    for i, k in enumerate(["One", "Two", "Three", "Five", "Ten", "All"])
)
_PATH = "web/path.png"
_HANDS = "hand_poses.png"

FIGS: dict[str, Fig] = {
    "hand-rest": Fig(
        _HANDS, "the hand at rest, the robotic finger straight", (30, 103, 690, 838), 1
    ),
    "hand-grasp": Fig(
        _HANDS, "the hand closed, as when imagining the hand", (720, 103, 1380, 838), 1
    ),
    "hand-finger": Fig(
        _HANDS, "the robotic sixth finger bent towards the palm", (1410, 103, 2070, 838), 1
    ),
    "system": Fig(
        "web/system.png",
        "the whole chain on one bench: cap, amplifier, a frame of signal, the model, the finger",
        (270, 0, 2045, 700),
    ),
    "rhythm": Fig(
        "web/rhythm.png", "the rhythm over the hand area while imagining, its resting size in grey"
    ),
    "sensors": Fig(
        "web/sensors.png",
        "the 40 sensors on a template head, the seven over the movement strip in white",
    ),
    "model": Fig(
        "web/model.png",
        "EEGNet as five stations: the signal in, rhythms, sensors, combining, the three lamps",
        (30, 120, 2320, 415),
    ),
    "leak": Fig(
        "web/leak.png",
        "the paper's way and the fair test on one round of trials; only what the first step "
        "learns from differs",
        small=13,
        checks=_LEAK + _PUBLISHED,
    ),
    "leak-slope": Fig(
        "web/leak-slope.png",
        "each patient scored the published way and fairly, one grey line each, the average in "
        "black",
        (0, 0, 1125, 650),
        small=12.5,
        checks=(*_LEAK, *_PUBLISHED, ("rqOneHOnePositive", "leak.n_positive", 1)),
    ),
    "dial-published": Fig(
        "web/dial-published.png",
        "a dial: the fair score (black needle) against the paper's way rebuilt (grey); the "
        "hatched arc is guessing",
        (0, 0, 783, 425),
        checks=_LEAK,
    ),
    "dial-use": Fig(
        "web/dial-use.png",
        "a dial: after the shortest practice, learned from other patients (black) against from "
        "nothing (grey)",
        (0, 0, 783, 425),
        checks=(
            ("rqTwoRestAhSfRctTslrKOneMean", "calibration.transfer.0.mean", 100),
            ("rqTwoRestAhSfTsLrKOneMean", "calibration.scratch.0.mean", 100),
            ("rqTwoMinutesKOne", "calibration.transfer.0.minutes", 1),
        ),
    ),
    "setup": Fig(
        "web/setup.png",
        "practice time against accuracy, learned from other patients (solid) and from nothing "
        "(dashed), 95% bands",
        small=12.5,
        checks=_CURVE,
    ),
    "switch-patients": Fig(
        "web/switch-patients.png",
        "each patient's dot for sixth finger or rest, and for hand or sixth finger",
        small=12.5,
        checks=(
            ("exFourTsLrCentralMean", "sixth.rest.mean", 100),
            ("exFourAhSfEegnetEaFtMean", "sixth.which.mean", 100),
        ),
    ),
    "switch-sure": Fig(
        "web/switch-sure.png",
        "acting only when sure: accuracy against the share of decisions taken, 95% band, the "
        "patients' own threshold as a diamond",
        small=12.5,
        checks=(
            ("exFourTsLrCentralSureMean", "sixth.sure.acc", 100),
            ("exFourTsLrCentralSureShare", "sixth.sure.share", 100),
            ("exFourTsLrCentralMean", "sixth.coverage.9.acc", 100),
        ),
    ),
    "switch-on": Fig(
        "web/switch-on.png",
        "what switches the finger on, every decision: resting, imagining the hand, imagining the "
        "sixth finger",
        small=13,
        checks=(
            ("exFourTsLrCentralFiresRestMean", "sixth.fires.rest.all", 100),
            ("exFourTsLrCentralFiresAhMean", "sixth.fires.hand.all", 100),
            ("exFourTsLrCentralFiresSfMean", "sixth.fires.finger.all", 100),
        ),
    ),
    "rhythm-measured": Fig(
        "web/rhythm-measured.png",
        "how much the rhythm fell in each patient, imagining the hand and the sixth finger",
        small=12.5,
        checks=(
            ("edaErdMuCThreeAhMean", "erd.affected_hand.mean", 1),
            ("edaErdMuCThreeSfMean", "erd.sixth_finger.mean", 1),
        ),
    ),
    "trial": Fig(
        "web/trial.png", "one trial as the patient sees it: rest, get ready, imagine", small=13.5
    ),
    "dial-command": Fig(
        "web/dial-command.png", "sixth finger or rest against hand or sixth finger", small=12.5
    ),
    "path-cap": Fig(_PATH, "cap and amplifier, drawn dashed: needed", (540, 170, 1030, 540)),
    "path-practice": Fig(
        _PATH, "the page and the model's server, drawn solid: built", (1165, 170, 1705, 540)
    ),
    "path-therapy": Fig(
        _PATH, "the board, motor and finger, drawn dashed: needed", (1850, 170, 2320, 540)
    ),
}


def data_at(data: dict, path: str) -> float:
    node: object = data
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return float(node)


@cache
def figure_png(key: str) -> tuple[bytes, int, int]:
    """The figure as placed: cropped, and laid on the page's off-white instead of white."""
    fig = FIGS[key]
    im = Image.open(FIGURES / fig.file)
    if im.mode == "RGBA":
        white = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(white, im)
    im = im.convert("RGB")
    if fig.crop:
        im = im.crop(fig.crop)
    if im.getpixel((0, 0)) == (255, 255, 255):
        # Multiplying keeps every shade and edge; only the white becomes the page.
        page = C["page"]
        bands = [
            band.point(lambda v, k=k: v * k // 255)
            for band, k in zip(im.split(), page, strict=True)
        ]
        im = Image.merge("RGB", bands)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue(), im.width, im.height


# Text measurement for the overflow check


def text_width(text: str, size: float, bold: bool) -> float:
    table = WIDTHS[bold]
    return sum(table.get(ch, 620) for ch in text) * size / 1000


def line_count(spans: list[Span], width: float, size: float, bold: bool) -> int:
    """Greedy word wrap, as PowerPoint does it, of one paragraph."""
    words: list[tuple[str, float, bool]] = []
    for sp in spans:
        sz = sp.size or size
        b = bold if sp.bold is None else sp.bold
        for word in re.split(r"(\s+)", sp.text):
            if word:
                words.append((word, sz * (0.6 if sp.sup else 1), b))
    lines, used = 1, 0.0
    for word, sz, b in words:
        w = text_width(word, sz, b)
        if word.isspace():
            used += w
            continue
        if used and used + w > width + 0.5:
            lines += 1
            used = w
        else:
            used += w
    return lines


# The deck


@dataclass
class TextBox:
    slide: int
    paras: list[list[Span]]
    size: float
    bold: bool
    x: float
    y: float
    w: float
    h: float
    spacing: float
    gap: float


@dataclass
class Record:
    no: int
    slide: Any
    kicker: str
    head: str
    seconds: int
    part: str
    tag: str | None = None
    say: str = ""
    numbers: list[tuple[str, str]] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    drawn: list[str] = field(default_factory=list)


class Deck:
    def __init__(self, macros: dict[str, Macro], data: dict) -> None:
        self.m = macros
        self.data = data
        self.prs = Presentation()
        self.prs.slide_width = Emu(int(W * 12700))
        self.prs.slide_height = Emu(int(H * 12700))
        self.records: list[Record] = []
        self.boxes: list[TextBox] = []
        self.rec: Any = None
        self._widen_template()

    # Template

    def _widen_template(self) -> None:
        """The default template is 4:3 with Calibri; make its master and layouts 16:9 and Inter."""
        master = self.prs.slide_master
        for shapes in [master.shapes, *[layout.shapes for layout in self.prs.slide_layouts]]:
            for shape in shapes:
                if shape._element.xpath("./p:spPr/a:xfrm"):
                    shape.left = int(shape.left * 4 / 3)
                    shape.width = int(shape.width * 4 / 3)
        theme = master.part.part_related_by(RT.THEME)
        xml = etree.fromstring(theme.blob)
        for latin in xml.iter(qn("a:latin")):
            if latin.getparent().tag in (qn("a:majorFont"), qn("a:minorFont")):
                latin.set("typeface", FONT)
        theme._blob = etree.tostring(xml, xml_declaration=True, encoding="UTF-8", standalone=True)
        master.background.fill.solid()
        master.background.fill.fore_color.rgb = C["page"]

    # Text

    def spans(self, template: str, record: bool = True, **style: object) -> list[Span]:
        """A template as runs, each {macro} filled in and noted on the current slide."""
        out: list[Span] = []
        pos = 0
        for m in PLACEHOLDER.finditer(template):
            if m.start() > pos:
                out.append(Span(template[pos : m.start()], **style))
            macro = self.m[m.group(1)]
            shown = show(macro, m.group(2) or "")
            for sp in shown:
                for k, v in style.items():
                    setattr(sp, k, v)
                out.append(sp)
            if record and self.rec is not None:
                text = "".join(f"^{sp.text}" if sp.sup else sp.text for sp in shown)
                self.rec.numbers.append((macro.name, text))
            pos = m.end()
        if pos < len(template):
            out.append(Span(template[pos:], **style))
        return out

    def plain(self, template: str, record: bool = True) -> str:
        """A template as plain text, for notes and the outline."""
        spans = self.spans(template, record)
        return "".join(f"^{sp.text}" if sp.sup else sp.text for sp in spans)

    def text(
        self,
        box: tuple[float, float, float, float],
        paras: str | list[str | list[Span]],
        size: float = 20,
        bold: bool = False,
        color: str = "ink",
        align: str = "l",
        anchor: str = "t",
        spacing: float = 1.0,
        gap: float = 0,
        italic: bool = False,
        serif: bool = False,
        free: bool = False,
        into: Any = None,
    ) -> Any:
        x, y, w, h = box
        if isinstance(paras, str):
            paras = [paras]
        resolved = [p if isinstance(p, list) else self.spans(p, free=free) for p in paras]
        shape = (into or self.rec.slide.shapes).add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
        style = (size, bold, color, align, anchor, spacing, gap, italic, serif)
        self._fill(shape.text_frame, resolved, *style)
        self.boxes.append(TextBox(self.rec.no, resolved, size, bold, x, y, w, h, spacing, gap))
        return shape

    def _fill(
        self,
        tf: Any,
        paras: list[list[Span]],
        size: float,
        bold: bool,
        color: str,
        align: str,
        anchor: str,
        spacing: float,
        gap: float,
        italic: bool = False,
        serif: bool = False,
    ) -> None:
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, side, 0)
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[
            anchor
        ]
        tf.text = ""
        for i, spans in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
            p.line_spacing = spacing
            if i > 0 and gap:
                p.space_before = Pt(gap)
            for sp in spans:
                r = p.add_run()
                r.text = sp.text
                f = r.font
                f.name = SERIF if (sp.serif or serif) else FONT
                f.size = Pt(sp.size or size)
                f.bold = bold if sp.bold is None else sp.bold
                f.italic = sp.italic or italic
                f.color.rgb = C[sp.color or color]
                if sp.sup:
                    f._rPr.set("baseline", "30000")

    # Slides

    def slide(
        self,
        kicker: str,
        head: str,
        seconds: int,
        say: str,
        tag: str | None = None,
        part: str = "talk",
        head_box: tuple[float, float, float, float] = (LEFT, HEAD_Y, BODY_W, HEAD_H),
        head_pt: float = HEAD_PT,
    ) -> Record:
        """A new slide with its question, its takeaway as the title, a tag and its number."""
        s = self.prs.slides.add_slide(self.prs.slide_layouts[5])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = C["page"]
        rec = Record(len(self.records) + 1, s, kicker, "", seconds, part, tag)
        self.records.append(rec)
        self.rec = rec
        title = s.shapes.title
        x, y, w, h = head_box
        title.left, title.top, title.width, title.height = Pt(x), Pt(y), Pt(w), Pt(h)
        spans = self.spans(head)
        self._fill(title.text_frame, [spans], head_pt, True, "ink", "l", "t", 1.0, 0)
        for r in title.text_frame.paragraphs[0].runs:
            r.font._rPr.set("spc", str(int(-0.02 * head_pt * 100)))
        self.boxes.append(TextBox(rec.no, [spans], head_pt, True, x, y, w, h, 1.0, 0))
        rec.head = "".join(f"^{sp.text}" if sp.sup else sp.text for sp in spans)
        rec.say = self.plain(say)
        edge = RIGHT - 52
        if tag:
            edge = self._tag(tag) - 16
        if kicker:
            self._kicker(kicker, edge)
        if part != "title":
            self._number()
        return rec

    def _kicker(self, kicker: str, edge: float) -> None:
        """The question the slide answers, its number in the page's italic serif."""
        num, _, ask = kicker.partition(" ")
        spans = [Span(num, serif=True, italic=True, size=20, free=True), Span("   ", size=18)]
        spans += self.spans(ask.strip(), size=18)
        self.text((LEFT, 20, edge - LEFT, 28), [spans], size=18, color="ink-3", anchor="b")

    def _tag(self, tag: str) -> float:
        w = text_width(tag, 18, False) + 28
        x = RIGHT - 52 - w
        pill = self.box(x, 18, w, 30, fill="chip", radius=15)
        self._fill(pill.text_frame, [[Span(tag)]], 18, False, "ink-2", "c", "m", 1.0, 0)
        box = TextBox(self.rec.no, [[Span(tag)]], 18, False, x + 14, 18, w - 28, 30, 1.0, 0)
        self.boxes.append(box)
        return x

    def _number(self) -> None:
        """The slide number as a field, so it stays right when the authors move slides."""
        no = self.rec.no
        tf = self.rec.slide.shapes.add_textbox(Pt(RIGHT - 40), Pt(20), Pt(40), Pt(28)).text_frame
        self._fill(tf, [[]], 18, False, "ink-3", "r", "b", 1.0, 0)
        fld = etree.SubElement(tf.paragraphs[0]._p, qn("a:fld"))
        fld.set("id", "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SITE}/{no}")).upper() + "}")
        fld.set("type", "slidenum")
        rpr = etree.SubElement(fld, qn("a:rPr"), lang="en-GB", sz="1800")
        fill = etree.SubElement(rpr, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), val=str(C["ink-3"]))
        etree.SubElement(rpr, qn("a:latin"), typeface=FONT)
        etree.SubElement(fld, qn("a:t")).text = str(no)

    # Shapes

    @staticmethod
    def _plain(shape: Any) -> None:
        # The theme's shape style would add its own outline and effects.
        el = shape._element
        style = el.find(qn("p:style"))
        if style is not None:
            el.remove(style)

    def _stroke(self, line: Any, color: str, lw: float, dash: str | bool | None) -> None:
        line.color.rgb = C[color]
        line.width = Pt(lw)
        if dash:
            line.dash_style = DASHES["dash" if dash is True else dash]

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str | None = None,
        line: str | None = None,
        lw: float = 1.0,
        dash: bool = False,
        radius: float = 0,
        oval: bool = False,
        into: Any = None,
    ) -> Any:
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
        shape = (into or self.rec.slide.shapes).add_shape(
            MSO_SHAPE.OVAL if oval else kind, Pt(x), Pt(y), Pt(w), Pt(h)
        )
        self._plain(shape)
        if radius and not oval:
            shape.adjustments[0] = min(0.5, radius / min(w, h))
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = C[fill]
        else:
            shape.fill.background()
        if line:
            self._stroke(shape.line, line, lw, dash)
        else:
            shape.line.fill.background()
        return shape

    def dot(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: str | None,
        line: str | None = None,
        lw: float = 1.5,
        into: Any = None,
    ) -> Any:
        return self.box(cx - r, cy - r, 2 * r, 2 * r, fill, line, lw, oval=True, into=into)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "ink",
        lw: float = 1.5,
        dash: str | None = None,
        into: Any = None,
    ) -> Any:
        shapes = into or self.rec.slide.shapes
        c = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Pt(x1), Pt(y1), Pt(x2), Pt(y2))
        self._plain(c)
        self._stroke(c.line, color, lw, dash)
        return c

    def path(
        self,
        pts: list[tuple[float, float]],
        color: str = "ink",
        lw: float = 2.0,
        dash: str | None = None,
        into: Any = None,
    ) -> Any:
        shapes = into or self.rec.slide.shapes
        fb = shapes.build_freeform(Pt(pts[0][0]), Pt(pts[0][1]), scale=1.0)
        fb.add_line_segments([(Pt(x), Pt(y)) for x, y in pts[1:]], close=False)
        shape = fb.convert_to_shape()
        self._plain(shape)
        shape.fill.background()
        self._stroke(shape.line, color, lw, dash)
        return shape

    def picture(
        self, key: str, box: tuple[float, float, float, float], align: str = "c", valign: str = "m"
    ) -> tuple[float, float, float, float]:
        """A figure as large as the box allows; fails if its smallest text would print too small."""
        x, y, w, h = box
        fig = FIGS[key]
        blob, pw, ph = figure_png(key)
        scale = min(w / pw, h / ph)
        dw, dh = pw * scale, ph * scale
        dx = x + {"l": 0, "c": (w - dw) / 2, "r": w - dw}[align]
        dy = y + {"t": 0, "m": (h - dh) / 2, "b": h - dh}[valign]
        printed = (fig.small or 0) * scale * fig.px_per_css
        if fig.small is not None and printed < MIN_PT - 0.05:
            raise ValueError(f"slide {self.rec.no}: {key}'s smallest text prints at {printed:.1f}")
        pic = self.rec.slide.shapes.add_picture(io.BytesIO(blob), Pt(dx), Pt(dy), Pt(dw), Pt(dh))
        pic._element.nvPicPr.cNvPr.set("descr", fig.shows[0].upper() + fig.shows[1:])
        if key not in self.rec.figures:
            self.rec.figures.append(key)
        return dx, dy, dw, dh

    def reading(self, x: float, y: float, w: float, rows: list[tuple[str, str, str]]) -> None:
        """The two lines under one of the page's dials: a mark, the value, what it is."""
        for i, (colour, value, what) in enumerate(rows):
            ry = y + i * 36
            self.line(x, ry + 15, x + 18, ry + 15, colour, 4)
            spans = self.spans(value, bold=True) + self.spans(what)
            tone = "ink" if i == 0 else "ink-3"
            self.text((x + 28, ry, w - 28, 32), [spans], size=22, color=tone)

    def group(self) -> Any:
        return self.rec.slide.shapes.add_group_shape().shapes

    # Checks and notes

    def check_figures(self) -> list[str]:
        problems = []
        for key in sorted({k for r in self.records for k in r.figures}):
            for name, path, factor in FIGS[key].checks:
                macro = self.m[name]
                value = value_of(macro)
                places = (
                    -value.as_tuple().exponent if isinstance(value.as_tuple().exponent, int) else 0
                )
                tolerance = Decimal(5).scaleb(-places - 1) + Decimal("1e-9")
                shown = Decimal(str(data_at(self.data, path))) * factor
                if abs(shown - value) > tolerance:
                    problems.append(f"{key}: data.json {path} = {shown} but \\{name} = {value}")
        return problems

    def check_text(self) -> list[str]:
        problems = []
        for b in self.boxes:
            sizes = [sp.size or b.size for p in b.paras for sp in p if not sp.sup]
            if sizes and min(sizes) < MIN_PT:
                problems.append(f"slide {b.slide}: text at {min(sizes)} pt")
            height = 0.0
            for i, p in enumerate(b.paras):
                if not p:
                    continue
                size = max(sp.size or b.size for sp in p)
                height += line_count(p, b.w, b.size, b.bold) * size * LINE * b.spacing
                if i:
                    height += b.gap
            if height > b.h + 2:
                text = "".join(sp.text for p in b.paras for sp in p)[:60]
                problems.append(f"slide {b.slide}: '{text}' needs {height:.0f} pt, has {b.h:.0f}")
            if b.x < 0 or b.y < 0 or b.x + b.w > W + 0.5 or b.y + b.h > H + 0.5:
                problems.append(f"slide {b.slide}: a text box leaves the slide")
            for p in b.paras:
                for sp in p:
                    if sp.macro or sp.free:
                        continue
                    loose = re.sub(FREE_DIGITS, "", sp.text)
                    if re.search(r"\d", loose):
                        problems.append(f"slide {b.slide}: a digit typed by hand in '{sp.text}'")
        return problems

    def check_shapes(self) -> list[str]:
        problems = []
        for rec in self.records:
            for shape in rec.slide.shapes:
                x, y = shape.left / 12700, shape.top / 12700
                right, bottom = x + shape.width / 12700, y + shape.height / 12700
                if x < -0.5 or y < -0.5 or right > W + 0.5 or bottom > H + 0.5:
                    problems.append(f"slide {rec.no}: '{shape.name}' leaves the slide")
        return problems

    def notes(self) -> None:
        talk = 0
        for rec in self.records:
            lines = []
            if rec.part == "backup":
                lines.append("Backup slide, for questions.")
            elif rec.part == "demo":
                lines.append(
                    f"Demo: {rec.seconds // 60}:{rec.seconds % 60:02d}, not part of the 15 minutes."
                )
            else:
                talk += rec.seconds
                lines.append(
                    f"Time: {rec.seconds // 60}:{rec.seconds % 60:02d} "
                    f"(by the end of this slide {talk // 60}:{talk % 60:02d} of 15:00)."
                )
            lines += ["", "Say: " + rec.say]
            if rec.numbers:
                lines += [
                    "",
                    "Numbers on this slide and in these notes, from paper/generated/numbers.tex:",
                ]
                seen = set()
                for name, shown in rec.numbers:
                    if (name, shown) in seen:
                        continue
                    seen.add((name, shown))
                    m = self.m[name]
                    lines.append(
                        f"- {shown}: \\{name} = {self.plain('{' + name + '}', record=False)} "
                        f"({m.source}; {m.meaning})"
                    )
            for key in rec.figures:
                fig = FIGS[key]
                lines += ["", f"Figure: docs/figures/{fig.file}, {fig.shows}."]
                if fig.file.startswith("web/") and fig.checks:
                    lines.append(
                        "Exported from the page by web/scripts/export-figures.mjs; its values "
                        "come from web/src/explain/data.json, which "
                        "scripts/make_web_explain_data.py writes from results/summary/."
                    )
                elif fig.file.startswith("web/"):
                    lines.append(
                        "A drawing of the page, exported by web/scripts/export-figures.mjs."
                    )
                else:
                    lines.append(
                        "A drawing of the page's hand, cut out of the picture without its labels."
                    )
                if fig.checks:
                    names = ", ".join(sorted({f"\\{n}" for n, _, _ in fig.checks}))
                    lines.append(
                        f"Its printed values equal {names} (checked when the deck is built)."
                    )
            for what in rec.drawn:
                lines += ["", what]
            text = "\n".join(lines)
            rec.slide.notes_slide.notes_text_frame.text = text


# The talk. Times in seconds; the main slides come to 15:00, the demo is apart.


def title_slide(d: Deck) -> None:
    d.slide(
        "",
        "Sixth-Finger BCI",
        20,
        "Good morning. We are Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman "
        "Lata. Our project asks whether a stroke patient's brain signals can move a robotic sixth "
        "finger, and the talk follows the questions an examiner would ask, one per slide.",
        part="title",
        head_box=(LEFT, 96, 540, 60),
        head_pt=44,
    )
    line = [
        Span("Imagine moving "),
        Span("a sixth finger", serif=True, italic=True, size=30),
        Span(", and a model that reads the brain's signals moves it."),
    ]
    d.text((LEFT, 166, 540, 100), [line], size=24)
    d.text(
        (LEFT, 282, 540, 48),
        "EEG-based adaptive brain–computer interface for novel artificial limb control",
        size=18,
        color="ink-3",
    )
    d.text(
        (LEFT, 352, 540, 60),
        [AUTHORS.replace(", ", " · "), "Guided by Dr. Suman Lata"],
        size=20,
        gap=4,
    )
    d.text(
        (LEFT, 430, 540, 70),
        "B.Tech minor project, Department of Electronics and Communication Engineering, Maharaja "
        "Surajmal Institute of Technology, New Delhi",
        size=18,
        color="ink-3",
    )
    d.picture("hand-finger", (600, 70, 316, 420))


def problem_slide(d: Deck) -> None:
    d.slide(
        "1 What problem does it solve?",
        "A stroke often leaves one hand too weak to grip; a robotic sixth finger worn on that "
        "wrist can grip for it",
        50,
        "Months after a stroke, one hand is often still weak: holding a cup, a bag or a phone "
        "with it is hard. A robotic finger worn on that wrist can press things against the palm, "
        "so the hand holds them again. The patient should not have to press a button to move it; "
        "they imagine moving it, and it moves.",
    )
    gap, ph = 48.0, 300.0
    pw = ph * 660 / 735
    x0 = LEFT + (BODY_W - 2 * pw - gap) / 2
    d.picture("hand-rest", (x0, BODY_Y, pw, ph))
    d.picture("hand-finger", (x0 + pw + gap, BODY_Y, pw, ph))
    d.text(
        (x0, BODY_Y + ph + 8, pw, 50), "The finger waits beside the weak hand", size=20, align="c"
    )
    d.text(
        (x0 + pw + gap, BODY_Y + ph + 8, pw, 50),
        "and bends to hold a thing against the palm",
        size=20,
        align="c",
    )
    d.text(
        (LEFT, 500, BODY_W, 26),
        "Extra robotic fingers: Prattichizzo et al., 2021. BCI therapy after stroke: Cervera et "
        "al., 2018.",
        size=18,
        color="ink-3",
        align="c",
    )


def bci_slide(d: Deck) -> None:
    rec = d.slide(
        "2 What are the sixth finger and a BCI?",
        "A brain-computer interface: an EEG cap reads the brain, and a model moves the finger "
        "when the wearer imagines it",
        60,
        "A brain-computer interface turns brain signals into a command without the body moving. "
        "Here the cap's sensors pick up the brain's tiny voltages, the amplifier passes the "
        "newest four seconds to the model, and the model says rest, hand or sixth finger; on "
        "sixth finger the robotic finger bends. Sensors on the scalp are safe and cheap but "
        "blurry; it recognises a trained pattern, it does not read thoughts.",
    )
    rec.drawn.append(WINDOW)
    x, y, w, _ = d.picture("system", (LEFT, BODY_Y, BODY_W, 300))
    crop = FIGS["system"].crop or (0, 0, 0, 0)
    k = w / (crop[2] - crop[0])
    # The drawn numbers are small; larger ones are laid exactly over them.
    centres = [(461, 382), (741, 434), (1039, 489), (1609.5, 593), (1820.5, 631)]
    for i, (cx, cy) in enumerate(centres, start=1):
        px, py = x + (cx - crop[0]) * k, y + (cy - crop[1]) * k
        d.dot(px, py, 14, "white", "ink-2", 1.5)
        d.text(
            (px - 14, py - 14, 28, 28), [[Span(str(i), free=True)]], size=18, align="c", anchor="m"
        )
    names = ["EEG cap", "Amplifier", "Frame of signal", "Model", "Robotic finger"]
    cw = BODY_W / len(names)
    for i, name in enumerate(names, start=1):
        spans = [Span(f"{i}  ", bold=True, free=True), Span(name)]
        d.text((LEFT + (i - 1) * cw, 470, cw, 28), [spans], size=20, align="c")


def rhythm_slide(d: Deck) -> None:
    d.slide(
        "2 What are the sixth finger and a BCI?",
        "The model looks for a rhythm over the hand area that weakens when a person imagines "
        "moving, by about as much for both",
        40,
        "Over the part of the brain that moves the hands there is a rhythm, called mu. When a "
        "person imagines moving, it weakens, though nothing moves: on average by "
        "{edaErdMuCThreeAhMean:abs}% for the hand and {edaErdMuCThreeSfMean:abs}% for the sixth "
        "finger; each dot is one patient. That fall is what every model here learns to spot, and "
        "because it is about the same for both, telling the hand from the finger is hard.",
        tag="Descriptive",
    )
    d.picture("rhythm-measured", (LEFT, BODY_Y, BODY_W, BODY_H))


def data_slide(d: Deck) -> None:
    rec = d.slide(
        "3 Whose data is it?",
        "We recorded no brain signals: we used a public recording of {nSubjects} stroke patients",
        50,
        "The recordings come from a public study by Wang and colleagues in Tianjin, China, free "
        "to use with credit. Each patient came three times: before two weeks of therapy, after "
        "it, and a month later. Each visit has four runs of trials; we always learn from runs 1 "
        "and 2 and test on runs 3 and 4, which the model has never seen.",
    )
    rec.drawn.append(DESIGN)
    g = d.group()
    bw, gap = (BODY_W - 3 * 24) / 4, 24.0
    sq, sg = 17.0, (bw - 10 * 17.0) / 9
    for run in range(4):
        x0 = LEFT + run * (bw + gap)
        d.text((x0, BODY_Y + 4, bw, 28), [[Span(f"Run {run + 1}")]], size=20, bold=True, into=g)
        for row in range(2):
            for col in range(10):
                x, y = x0 + col * (sq + sg), BODY_Y + 40 + row * (sq + 5)
                if run < 2:
                    d.box(x, y, sq, sq, fill="hand", radius=3, into=g)
                else:
                    d.box(x, y, sq, sq, line="ink-2", lw=1.25, radius=3, into=g)
    ly = BODY_Y + 96
    d.line(LEFT, ly, LEFT + 2 * bw + gap, ly, "ink-2", 2.5, into=g)
    d.line(LEFT + 2 * (bw + gap), ly, RIGHT, ly, "ink-2", 2.5, dash="dash", into=g)
    d.text((LEFT, ly + 10, 2 * bw, 28), "the model learns", size=20, color="ink-2", into=g)
    d.text(
        (LEFT + 2 * (bw + gap), ly + 10, 2 * bw, 28),
        "the model is tested",
        size=20,
        color="ink-2",
        into=g,
    )
    d.line(LEFT, BODY_Y + 168, RIGHT, BODY_Y + 168, "rule", 1, into=g)
    sy = BODY_Y + 190
    spots = [
        (LEFT, "l", "before therapy"),
        (LEFT + BODY_W / 2 - 100, "c", "after therapy"),
        (RIGHT - 200, "r", "follow-up"),
    ]
    for i, (x, align, sub) in enumerate(spots, start=1):
        d.text(
            (x, sy, 200, 56), [[Span(f"Session {i}", bold=True)], sub], size=20, align=align, into=g
        )
    for x1, x2, label in [
        (LEFT + 170, LEFT + BODY_W / 2 - 80, "two weeks of therapy"),
        (LEFT + BODY_W / 2 + 80, RIGHT - 130, "a month"),
    ]:
        d.line(x1, sy + 44, x2, sy + 44, "ink-4", 1.5, dash="dash", into=g)
        d.text((x1, sy + 12, x2 - x1, 26), label, size=18, color="ink-3", align="c", into=g)
    d.text(
        (LEFT, 480, BODY_W, 44),
        "Wang et al., Scientific Data, 2026. Recorded in Tianjin, China; free to use with credit "
        "(CC BY 4.0).",
        size=18,
        color="ink-3",
    )
    rec.drawn.append(
        "Drawn on the slide from the dataset's design (runs, trials and sessions as the dataset "
        "paper gives them), as the page's figure docs/figures/web/session.png draws it."
    )


def meaning_slide(d: Deck) -> None:
    rec = d.slide(
        "4 The paper reports {rqOnePublishedGroupBCspLda:int}%. Is that right?",
        "The paper's {rqOnePublishedGroupBCspLda:int}%: how often its method told an imagined "
        "hand from an imagined sixth finger",
        40,
        "The dataset's own paper reports {rqOnePublishedGroupBCspLda:int}% (from "
        "{rqOnePublishedGroupBCspLda} to {rqOnePublishedGroupTCspLda}% in its two groups). That "
        "means: shown a few seconds of brain signal from one trial, its method had to say hand or "
        "sixth finger, and it was right that often. Guessing is right half the time, so "
        "{rqOnePublishedGroupBCspLda:int}% would be a usable two-command device.",
    )
    rec.drawn.append(WINDOW)
    gap, ph = 150.0, 290.0
    pw = ph * 660 / 735
    x0 = LEFT + (BODY_W - 2 * pw - gap) / 2
    d.picture("hand-grasp", (x0, BODY_Y + 6, pw, ph))
    d.picture("hand-finger", (x0 + pw + gap, BODY_Y + 6, pw, ph))
    d.text(
        (x0 + pw, BODY_Y + 6 + ph / 2 - 24, gap, 48),
        "or",
        size=36,
        color="ink-3",
        align="c",
        anchor="m",
        serif=True,
        italic=True,
    )
    d.text((x0 - 40, BODY_Y + ph + 14, pw + 80, 28), "Imagine moving the hand", size=20, align="c")
    d.text(
        (x0 + pw + gap - 40, BODY_Y + ph + 14, pw + 80, 28),
        "Imagine moving the sixth finger",
        size=20,
        align="c",
    )
    d.text(
        (LEFT, 486, BODY_W, 30),
        "Guessing would be right half the time.",
        size=20,
        color="ink-3",
        align="c",
    )


def leak_slide(d: Deck) -> None:
    d.slide(
        "4 The paper reports {rqOnePublishedGroupBCspLda:int}%. Is that right?",
        "Too high: the method's first step studied the test trials too, an exam seen in advance",
        60,
        "The method has two steps, CSP then LDA. In the published code the first step learned "
        "from every trial, the test trials included, before it was tested on them. We rebuilt the "
        "method from the authors' code and changed only that: the first step learns from the "
        "learning trials alone. Our rebuild of the published way gives "
        "{rqOneCspLdaPaperReplicaMean}%, close to the paper's figure.",
        tag="Pre-registered test",
    )
    d.picture("leak", (LEFT, BODY_Y, BODY_W, BODY_H))


def fair_slide(d: Deck) -> None:
    d.slide(
        "4 The paper reports {rqOnePublishedGroupBCspLda:int}%. Is that right?",
        "Tested fairly, the same method scores {rqOneCspLdaCvLeakfreeMean}%: barely better than "
        "guessing, and lower for all {rqOneHOnePositive} patients",
        45,
        "Tested fairly, the same method is right {rqOneCspLdaCvLeakfreeMean}% of the time against "
        "{rqOneCspLdaPaperReplicaMean}% the published way, a drop of {rqOneHOneDiff} points (95% "
        "interval {rqOneHOneDiffCiLo} to {rqOneHOneDiffCiHi}), lower for all {rqOneHOnePositive} "
        "of {rqOneHOneN} patients, p = {rqOneHOneP}. This was our pre-registered hypothesis H1, "
        "and it held. We do not say the authors were dishonest; it is a common and subtle mistake.",
        tag="Pre-registered test",
    )
    x, y, w, h = d.picture("dial-published", (LEFT, BODY_Y, 470, BODY_H - 90), valign="t")
    d.reading(
        x + 40,
        y + h + 14,
        w - 40,
        [
            ("ink", "{rqOneCspLdaCvLeakfreeMean}%", " tested fairly"),
            ("ink-4", "{rqOneCspLdaPaperReplicaMean}%", " the paper's way, rebuilt"),
        ],
    )
    rows = [
        ("At {rqOnePublishedGroupBCspLda:int}%", "a usable two-command device"),
        ("At {rqOneCspLdaCvLeakfreeMean}%", "barely above guessing"),
    ]
    for i, (big, small) in enumerate(rows):
        y = BODY_Y + 80 + i * 120
        d.text((560, y, 356, 44), big, size=34, bold=True, color="ink" if i else "ink-3")
        d.text((560, y + 46, 356, 56), small, size=22, color="ink-2")


def methods_slide(d: Deck) -> None:
    rec = d.slide(
        "5 What are CSP, LDA and EEGNet?",
        "CSP and LDA are the paper's two-step method; EEGNet, the model in our demo, learns both "
        "steps from examples",
        50,
        "CSP, common spatial patterns, learns how to mix the sensors so that the two imagined "
        "movements differ as much as possible. LDA, linear discriminant analysis, then draws a "
        "straight line between the two in what CSP gives it. EEGNet is a small neural network "
        "built for EEG that learns which sensors and which rhythms matter by itself; it is the "
        "model the demo runs.",
    )
    half = (BODY_W - 40) / 2
    d.picture("sensors", (LEFT, BODY_Y, 140, 176))
    d.text(
        (LEFT + 156, BODY_Y + 8, half - 156, 170),
        [
            [Span("CSP", bold=True, size=22)],
            "mixes the sensors so the two imagined movements differ as much as possible",
        ],
        size=20,
        gap=4,
    )
    g = d.group()
    lx, ly = LEFT + half + 40, BODY_Y + 10
    hand = [(18, 112), (34, 140), (52, 118), (26, 160), (60, 150), (44, 96), (72, 132), (12, 138)]
    finger = [(104, 30), (122, 58), (138, 36), (96, 64), (150, 70), (118, 14), (140, 92), (164, 46)]
    for px, py in hand:
        d.dot(lx + px, ly + py, 6, "hand", into=g)
    for px, py in finger:
        d.dot(lx + px, ly + py, 6, "sixth", into=g)
    d.line(lx + 8, ly + 40, lx + 168, ly + 168, "ink-2", 2, dash="dash", into=g)
    rec.drawn.append(
        "The LDA picture is a sketch of the idea, not data: grey for hand trials, orange for "
        "sixth-finger trials."
    )
    d.text(
        (lx + 196, BODY_Y + 8, half - 196, 170),
        [[Span("LDA", bold=True, size=22)], "draws a straight line between the two movements"],
        size=20,
        gap=4,
    )
    d.line(LEFT, BODY_Y + 196, RIGHT, BODY_Y + 196, "rule", 1)
    d.picture("model", (LEFT, BODY_Y + 212, BODY_W, 112))
    d.text(
        (LEFT, BODY_Y + 334, BODY_W, 56),
        [
            [
                Span("EEGNet ", bold=True, size=22),
                Span(
                    "is a small neural network for EEG that learns, from examples, which sensors "
                    "and rhythms tell the choices apart."
                ),
            ]
        ],
        size=20,
    )


def headstart_slide(d: Deck) -> None:
    d.slide(
        "6 How much practice does a new patient need?",
        "Learning from other patients, a new patient starts at {rqTwoRestAhSfRctTslrKOneMean}% "
        "after {rqTwoMinutesKOne:sec} s of practice; from nothing, {rqTwoRestAhSfTsLrKOneMean}%",
        50,
        "Every brain is a little different, so the model needs a few practice trials from each "
        "new patient, here choosing among rest, hand and sixth finger, where guessing gets a "
        "third. With one trial of each, about {rqTwoMinutesKOne:sec} seconds, a model that "
        "already learned from the other patients is right {rqTwoRestAhSfRctTslrKOneMean}% of the "
        "time, against {rqTwoRestAhSfTsLrKOneMean}% starting from nothing; from nothing it needs "
        "{rqTwoMinutesKTen} minutes to reach the same {rqTwoRestAhSfTsLrKTenMean}%. This was "
        "hypothesis H2a, pre-registered, p = {rqTwoHTwoAP}, and it held again after therapy.",
        tag="Pre-registered test",
    )
    x, y, w, h = d.picture("dial-use", (LEFT, BODY_Y, 470, BODY_H - 90), valign="t")
    d.reading(
        x + 40,
        y + h + 14,
        w - 40,
        [
            ("ink", "{rqTwoRestAhSfRctTslrKOneMean}%", " from other patients"),
            ("ink-4", "{rqTwoRestAhSfTsLrKOneMean}%", " from nothing"),
        ],
    )
    rows = [
        ("{rqTwoMinutesKOne:sec} s", "of practice, after learning from other patients", "ink"),
        (
            "{rqTwoMinutesKTen} min",
            "of practice from nothing, to reach the same {rqTwoRestAhSfTsLrKTenMean}%",
            "ink-3",
        ),
    ]
    for i, (big, small, colour) in enumerate(rows):
        y = BODY_Y + 60 + i * 140
        d.text((560, y, 356, 50), big, size=40, bold=True, color=colour)
        d.text((560, y + 52, 356, 60), small, size=20, color="ink-2")


def curve_slide(d: Deck) -> None:
    d.slide(
        "6 How much practice does a new patient need?",
        "Then it levels off, and starting from nothing overtakes it: {rqTwoRestAhSfTsLrKAllMean}% "
        "against {rqTwoRestAhSfRctTslrKAllMean}% after {rqTwoMinutesKAll} min",
        60,
        "Learning from other patients is a head start, not a better model. It stays near "
        "{rqTwoRestAhSfRctTslrKAllMean}% however much the patient practises, while the patient's "
        "own model keeps learning and passes it: {rqTwoRestAhSfTsLrKAllMean}% after "
        "{rqTwoMinutesKAll} minutes. That the advantage shrinks with practice was hypothesis H2b, "
        "pre-registered, p = {rqTwoHTwoBP}. The shaded bands show where the true average very "
        "likely lies with only {rqTwoHTwoAN} patients.",
        tag="Pre-registered test",
    )
    d.picture("setup", (LEFT, BODY_Y, BODY_W, BODY_H))


def switch_slide(d: Deck) -> None:
    d.slide(
        "7 Can the sixth finger be a command of its own?",
        "As a “move now” switch it works: told from rest {exFourTsLrCentralMean:int}% of the "
        "time, but from the hand only {exFourAhSfEegnetEaFtMean}%",
        50,
        "Each dot is one patient. Told apart from resting, imagining the sixth finger is "
        "recognised {exFourTsLrCentralMean}% of the time by a simple model reading the sensors "
        "over the movement strip; {exFourTsLrCentralNAtLeastEighty} of {rqOneHOneN} patients "
        "reach eighty percent or more. Told apart from imagining the hand it is right only "
        "{exFourAhSfEegnetEaFtMean}%, even with a network pre-trained on the other patients. "
        "These are exploratory follow-ups, run after the main results.",
        tag="Exploratory",
    )
    d.picture("switch-patients", (LEFT, BODY_Y, BODY_W, BODY_H))


def sure_slide(d: Deck) -> None:
    d.slide(
        "7 Can the sixth finger be a command of its own?",
        "Acting only when it is sure, the switch is right {exFourTsLrCentralSureMean:int}% of the "
        "time, on {exFourTsLrCentralSureShare}% of the decisions",
        35,
        "The model can hold back when it is unsure. How sure it must be was set for each patient "
        "on their practice runs only. It then acts on {exFourTsLrCentralSureShare}% of the "
        "decisions and is right on {exFourTsLrCentralSureMean}% of those; while the patient rests "
        "it moves the finger by mistake {exFourTsLrCentralFiresRestSureMean}% of the time.",
        tag="Exploratory",
    )
    d.picture("switch-sure", (LEFT, BODY_Y, BODY_W, BODY_H))


def hand_too_slide(d: Deck) -> None:
    d.slide(
        "7 Can the sixth finger be a command of its own?",
        "But imagining the hand switches it on too, {exFourTsLrCentralFiresAhMean}% of the time: "
        "it is not yet a command apart from the hand",
        45,
        "The switch never learned from an imagined hand movement, yet those switch it on "
        "{exFourTsLrCentralFiresAhMean}% of the time, nearly as often as the sixth finger, "
        "{exFourTsLrCentralFiresSfMean}%. So it detects that a movement is being imagined, not "
        "which one. Two movements of one hand are hard to tell apart even in healthy people; the "
        "backup slides have that benchmark.",
        tag="Exploratory",
    )
    d.picture("switch-on", (LEFT, BODY_Y + 40, BODY_W, 200))
    d.text(
        (LEFT, 430, BODY_W, 60),
        "Share of decisions that switch the finger on. The switch learned only resting and the "
        "sixth finger.",
        size=20,
        color="ink-3",
        align="c",
    )


def later_slide(d: Deck) -> None:
    rec = d.slide(
        "8 Does it work on another day, and live?",
        "On another day the model needs a top-up: unchanged it falls to "
        "{rqFourLaterPostUnchangedMean}%, and {rqTwoMinutesKFive} min of practice restores "
        "{rqFourLaterPostRecentredKFiveMean}%",
        45,
        "A model built on the first visit scores {rqTwoRestAhSfTsLrKAllMean}% that day. Two weeks "
        "later, unchanged, it falls to {rqFourLaterPostUnchangedMean}%, because the cap sits "
        "differently and the brain may have changed. Five practice trials of each movement, about "
        "{rqTwoMinutesKFive} minutes, bring it back to {rqFourLaterPostRecentredKFiveMean}%; a "
        "month later the same top-up gives {rqFourLaterFollowRecentredKFiveMean}%. A real device "
        "would need a short practice at the start of each session.",
        tag="Descriptive",
    )
    g = d.group()
    rows = [
        ("On the day it was built", "", "{rqTwoRestAhSfTsLrKAllMean}", "ink-3"),
        ("Two weeks later", "unchanged", "{rqFourLaterPostUnchangedMean}", "ink-4"),
        (
            "",
            "after {rqTwoMinutesKFive} min of practice",
            "{rqFourLaterPostRecentredKFiveMean}",
            "ink",
        ),
        ("A month later", "unchanged", "{rqFourLaterFollowUnchangedMean}", "ink-4"),
        (
            "",
            "after {rqTwoMinutesKFive} min of practice",
            "{rqFourLaterFollowRecentredKFiveMean}",
            "ink",
        ),
    ]
    x0, x1 = LEFT + 470, RIGHT - 110
    top, step = BODY_Y + 10, 58.0
    for i, (when, how, value, colour) in enumerate(rows):
        y = top + i * step + (14 if i >= 1 else 0) + (14 if i >= 3 else 0)
        if when:
            d.text((LEFT, y, 200 if how else 440, 34), when, size=20, bold=True, anchor="m", into=g)
        if how:
            strong = colour == "ink"
            d.text(
                (LEFT + 190, y, 270, 34),
                how,
                size=20,
                color="ink" if strong else "ink-2",
                anchor="m",
                into=g,
            )
        d.box(x0, y + 8, x1 - x0, 18, fill="chip", radius=4, into=g)
        frac = float(value_of(d.m[PLACEHOLDER.match(value).group(1)])) / 100
        d.box(x0, y + 8, (x1 - x0) * frac, 18, fill=colour, radius=4, into=g)
        d.text((x1 + 12, y, 98, 34), value + "%", size=22, bold=True, align="r", anchor="m", into=g)
    gx = x0 + (x1 - x0) / 3
    bottom = top + 5 * step + 28
    d.line(gx, top - 4, gx, bottom - 18, "ink-3", 1.25, dash="dash", into=g)
    d.text((gx - 60, bottom - 14, 120, 26), "guessing", size=18, color="ink-3", align="c")
    d.text(
        (LEFT, 494, BODY_W, 30),
        "{rqFourLaterPostUnchangedN} patients two weeks later, {rqFourLaterFollowUnchangedN} a "
        "month later; three choices: rest, hand or sixth finger.",
        size=18,
        color="ink-3",
    )
    rec.drawn.append(
        "Bars drawn on the slide from the macros above "
        "(results/summary/rq4_longitudinal_table.csv, calib_curves.csv), as "
        "docs/figures/web/later.png and later-adjusted.png draw them."
    )


def live_slide(d: Deck) -> None:
    rec = d.slide(
        "8 Does it work on another day, and live?",
        "Played as if live, it catches {rqFourSwitchEegnetScratchDetectMean}% of imagined "
        "movements but switches on by mistake {rqFourSwitchEegnetScratchFalsePerMinMean} times a "
        "minute at rest",
        45,
        "Here each patient's test runs were played start to end as if live: every half second the "
        "model reads the newest four seconds, and nobody tells it when the instruction came. It "
        "catches {rqFourSwitchEegnetScratchDetectMean}% of imagined movements, about "
        "{rqFourSwitchEegnetScratchLatencyMean:1} seconds after imagining starts, but switches on "
        "by mistake {rqFourSwitchEegnetScratchFalsePerMinMean} times a minute of rest: too often "
        "for a device yet. A simpler model on the central sensors catches {exFiveMoveDetectMean}% "
        "with {exFiveMoveFalsePerMinMean} mistakes a minute; no variant caught more. This "
        "one-switch view was added after the results, so it is exploratory.",
        tag="Exploratory",
    )
    rec.drawn.append(REPLAY)
    g = d.group()
    tiles = [
        ("{rqFourSwitchEegnetScratchDetectMean}%", "of imagined movements switch it on"),
        ("{rqFourSwitchEegnetScratchLatencyMean:1} s", "from the start of imagining"),
        ("{rqFourSwitchEegnetScratchFalsePerMinMean}", "mistaken switch-ons per minute of rest"),
    ]
    tw = BODY_W / 3
    for i, (big, small) in enumerate(tiles):
        x = LEFT + i * tw
        if i:
            d.line(x, BODY_Y + 60, x, BODY_Y + 250, "rule", 1.25, into=g)
        d.text(
            (x + 20, BODY_Y + 70, tw - 40, 76),
            big,
            size=56,
            bold=True,
            align="c",
            into=g,
        )
        d.text(
            (x + 30, BODY_Y + 160, tw - 60, 60), small, size=20, color="ink-2", align="c", into=g
        )
    d.text(
        (LEFT, 440, BODY_W, 60),
        "Nobody tells the model when the instruction came; it reads the newest stretch of signal "
        "again and again. Average of {rqFourSwitchN} patients.",
        size=20,
        color="ink-3",
        align="c",
    )


def demo_slide(d: Deck) -> None:
    rec = d.slide(
        "Demo Can we see it work?",
        "A recording the model never learned from, played at real speed: when the patient "
        "imagines moving, the finger bends",
        DEMO_SECONDS,
        "This is patient {demoSubject}. The model learned from this patient's first two runs "
        "only, {demoTrainingTrials} trials; what plays now is the last two runs, {demoTrials} "
        "whole trials it has never seen, at real speed. Left is what the patient is told, the "
        "middle is their brain signal, right is the model's reading with a tick or a cross. On "
        "this patient it is right {demoHeldOutAcc}% on three choices, {demoMoveRestRight} of "
        "{demoMoveRestN} for move or rest, {demoHandFingerRight} of {demoHandFingerN} for hand or "
        "sixth finger. Per trial reads the stretch after each instruction, as the study tests "
        "it; Continuous reads the newest stretch again and again without knowing when the "
        "instruction came, as a real device would, and catches less. If the page does not load, "
        "play the recorded video (~/Movies/sixth-finger-bci-demo-backup.mp4, also on the USB "
        "stick).",
        part="demo",
    )
    rec.drawn += [WINDOW, REPLAY]
    d.picture("hand-finger", (600, BODY_Y, 316, BODY_H))
    d.text((LEFT, BODY_Y + 60, 520, 48), SITE + "/live", size=32, bold=True)
    d.text(
        (LEFT, BODY_Y + 130, 520, 200),
        [
            "Left: what the patient is told",
            "Middle: their brain signal",
            "Right: what the model reads, right or wrong",
        ],
        size=22,
        color="ink-2",
        gap=10,
    )


def built_slide(d: Deck) -> None:
    d.slide(
        "9 What is built, and what is not?",
        "Built: the model, its server and this page. Not built: the live headset link and the "
        "robotic finger",
        50,
        "Solid parts are built in this project, dashed parts are what a real system still needs. "
        "The model, its server and the page are built and run on real recordings; the model also "
        "runs inside the browser. The live headset, the bridge that would stream its signal, and "
        "the board, motor and finger are not built: the command leaves the model, but nothing "
        "physical moves yet.",
    )
    cols = [
        ("path-cap", "Cap on", [("Cap and amplifier: needed", False)]),
        (
            "path-practice",
            "Practice",
            [
                ("This page: built", True),
                ("Bridge to the headset: needed", False),
                ("Server and model: built", True),
            ],
        ),
        ("path-therapy", "Therapy", [("Board, motor and finger: needed", False)]),
    ]
    cw = BODY_W / 3
    for i, (key, name, parts) in enumerate(cols):
        x = LEFT + i * cw
        d.picture(key, (x + 10, BODY_Y, cw - 20, 150), valign="b")
        d.text((x + 10, BODY_Y + 160, cw - 20, 32), name, size=24, bold=True)
        y = BODY_Y + 200
        for part, built in parts:
            lines = line_count([Span(part)], cw - 52, 20, False)
            d.box(
                x + 10,
                y + 5,
                22,
                16,
                fill="rule" if built else None,
                line="ink" if built else "ink-3",
                lw=1.25,
                dash=not built,
                radius=3,
            )
            d.text(
                (x + 42, y, cw - 52, lines * 25), part, size=20, color="ink" if built else "ink-2"
            )
            y += lines * 25 + 10
    ky = 496
    d.box(LEFT, ky + 5, 22, 16, fill="rule", line="ink", lw=1.25, radius=3)
    d.text((LEFT + 32, ky, 240, 28), "Built in this project", size=18, color="ink-2")
    d.box(LEFT + 290, ky + 5, 22, 16, line="ink-3", lw=1.25, dash=True, radius=3)
    d.text((LEFT + 322, ky, 280, 28), "Needed in a real system", size=18, color="ink-2")


def added_slide(d: Deck) -> None:
    d.slide(
        "10 What did we add?",
        "What is new is a fair test of what was already there, fixed in advance and open to check",
        50,
        "The recordings, the paper's method and the models already existed. What we add is a fair "
        "test of them: the published score measured fairly, the same mistake measured in other "
        "datasets, a check of the shared recordings, how fast a new patient can start, and what "
        "the sixth finger can be used as today. Every main test was written down before it was "
        "run, and the code, the results and the data audit are open.",
    )
    g = d.group()
    tiles = [
        (
            "{rqOnePublishedGroupBCspLda:int}% to {rqOneCspLdaCvLeakfreeMean}%",
            "the paper's score, tested fairly",
        ),
        (
            "+{rqOneBnciHOneBDiff} to +{rqFiveModmaTsLrInflation}",
            "points from the same mistake in other datasets",
        ),
        ("{auditPairsScreened} pairs", "of runs compared to check the shared recordings"),
        (
            "{rqTwoMinutesKOne:sec} s vs {rqTwoMinutesKTen} min",
            "of practice for a new patient, with and without other patients",
        ),
        ("{exFourTsLrCentralMean:int}%", "the sixth finger as a “move now” switch, exploratory"),
        (
            "{exThreeBenchPairsMin} to {exThreeBenchPairsMax}%",
            "two grasps of one hand in healthy people, a week apart, exploratory",
        ),
    ]
    tw, th = (BODY_W - 2 * 24) / 3, 170.0
    for i, (big, small) in enumerate(tiles):
        x = LEFT + (i % 3) * (tw + 24)
        y = BODY_Y + 8 + (i // 3) * (th + 24)
        d.box(x, y, tw, th, fill="white", line="rule", lw=1, radius=14, into=g)
        d.text((x + 20, y + 22, tw - 40, 44), big, size=28, bold=True, into=g)
        d.text((x + 20, y + 74, tw - 40, 84), small, size=20, color="ink-2", into=g)


def next_slide(d: Deck) -> None:
    d.slide(
        "11 What is next?",
        "Next: a study with a live headset, a real finger, and a switch that rarely fires at rest",
        40,
        "First, a closed-loop study: patients see the finger answer while they practise, which "
        "lets them adapt to the model. Second, a physical finger: a board with joint limits and "
        "an emergency stop, fed by live EEG. Third, a better switch: fewer false starts at rest, "
        "then a command apart from the hand, tested on other patients and centres.",
    )
    cols = [
        ("path-cap", "A closed-loop study", "patients see the finger answer while they practise"),
        ("path-therapy", "A physical finger", "a board with joint limits and an emergency stop"),
        (
            "hand-grasp",
            "A better switch",
            "fewer false starts at rest, then a command apart from the hand",
        ),
    ]
    cw = BODY_W / 3
    for i, (key, name, what) in enumerate(cols):
        x = LEFT + i * cw
        d.picture(key, (x + 20, BODY_Y, cw - 40, 190), valign="b")
        d.text((x + 14, BODY_Y + 210, cw - 28, 34), name, size=24, bold=True, align="c")
        d.text((x + 14, BODY_Y + 250, cw - 28, 90), what, size=20, color="ink-2", align="c")


def close_slide(d: Deck) -> None:
    d.slide(
        "",
        "Thank you. Questions?",
        15,
        "Thank you. We are happy to take questions; the backup slides after this one cover the "
        "leak patient by patient, the same mistake in other data, every calibration method, the "
        "healthy benchmark, the live replay and the demo patient.",
        head_box=(LEFT, 150, 520, 60),
        head_pt=44,
    )
    d.text((LEFT, 236, 540, 44), SITE, size=30, bold=True)
    d.text(
        (LEFT, 290, 540, 60),
        "The page, the live demo and every answer in this talk.",
        size=20,
        color="ink-2",
    )
    d.text(
        (LEFT, 400, 540, 60),
        [AUTHORS.replace(", ", " · "), "Guided by Dr. Suman Lata"],
        size=20,
        color="ink-2",
        gap=4,
    )
    d.picture("hand-finger", (600, 70, 316, 420))


# Backup slides


def backup_leak(d: Deck) -> None:
    d.slide(
        "Backup  The leak, patient by patient",
        "Patient by patient, the fair score is lower for all {rqOneHOnePositive}, by "
        "{rqOneHOneDiffMin} to {rqOneHOneDiffMax} points",
        0,
        "Each grey line is one patient, scored the published way on the left and fairly on the "
        "right; the black line is the average, {rqOneCspLdaPaperReplicaMean}% falling to "
        "{rqOneCspLdaCvLeakfreeMean}%. The mean drop is {rqOneHOneDiff} points, 95% interval "
        "{rqOneHOneDiffCiLo} to {rqOneHOneDiffCiHi}, Wilcoxon p = {rqOneHOneP}; without the two "
        "patients used to set up the pipeline it is {rqOneHOneNoDevDiff} points, and after "
        "therapy {rqOneHOnePostDiff}.",
        tag="Pre-registered test",
        part="backup",
    )
    x, y, w, h = d.picture("leak-slope", (LEFT, BODY_Y, 560, 330))
    k = w / 375
    d.text(
        (x, y + h + 6, 150 * k, 56),
        [[Span("The published way", bold=True)], "test trials also used"],
        size=18,
        align="c",
    )
    d.text(
        (x + w - 170 * k, y + h + 6, 150 * k, 56),
        [[Span("Tested fairly", bold=True)], "test trials kept apart"],
        size=18,
        align="c",
    )
    d.text(
        (640, BODY_Y + 40, 276, 300),
        [
            "Mean drop {rqOneHOneDiff} points",
            "95% interval {rqOneHOneDiffCiLo} to {rqOneHOneDiffCiHi}",
            [Span("p = "), *d.spans("{rqOneHOneP}")],
            "{rqOneHOneN} patients",
        ],
        size=22,
        gap=12,
    )


def backup_elsewhere(d: Deck) -> None:
    rec = d.slide(
        "Backup  The same mistake elsewhere",
        "The same mistake raised the score in every other dataset we tried, by "
        "{rqOneBnciHOneBDiff} to {rqFiveModmaTsLrInflation} points",
        0,
        "We repeated the check on two public datasets of imagined hand movements in healthy "
        "people: {rqOneBnciHOneBDiff} points on BNCI 2014-001 and {rqOneChoHOneBDiff} on Cho "
        "2017, both pre-registered as H1b. As a side check on the same kind of mistake in another "
        "field, depression from resting EEG: when one person's segments sit on both sides of the "
        "split, the score rises by {rqFiveMumtazBpLrInflation} to {rqFiveMumtazTsLrInflation} "
        "points on Mumtaz and {rqFiveModmaBpLrInflation} to {rqFiveModmaTsLrInflation} on MODMA; "
        "with the diagnoses shuffled it still scores {rqFiveShuffledSegmentCvMean}%, so the model "
        "recognises people, not depression.",
        tag="Pre-registered tests",
        part="backup",
    )
    g = d.group()
    rows = [
        ("Imagined movement", None, None, None),
        (
            "These stroke patients ({rqOneHOneN})",
            "rqOneCspLdaPaperReplicaMean",
            "rqOneCspLdaCvLeakfreeMean",
            "{rqOneCspLdaPaperReplicaMean}% to {rqOneCspLdaCvLeakfreeMean}%",
        ),
        (
            "BNCI 2014-001, healthy ({rqOneBnciHOneBN})",
            "rqOneBnciPaperReplicaMean",
            "rqOneBnciCvLeakfreeMean",
            "{rqOneBnciPaperReplicaMean}% to {rqOneBnciCvLeakfreeMean}%",
        ),
        (
            "Cho 2017, healthy ({rqOneChoHOneBN})",
            "rqOneChoPaperReplicaMean",
            "rqOneChoCvLeakfreeMean",
            "{rqOneChoPaperReplicaMean}% to {rqOneChoCvLeakfreeMean}%",
        ),
        ("Depression from resting EEG", None, None, None),
        (
            "Mumtaz, frequency bands ({rqFiveMumtazBpLrN})",
            "rqFiveMumtazBpLrSegmentCvBa",
            "rqFiveMumtazBpLrSubjectCvBa",
            "{rqFiveMumtazBpLrSegmentCvBa}% to {rqFiveMumtazBpLrSubjectCvBa}%",
        ),
        (
            "Mumtaz, sensor pairs ({rqFiveMumtazTsLrN})",
            "rqFiveMumtazTsLrSegmentCvBa",
            "rqFiveMumtazTsLrSubjectCvBa",
            "{rqFiveMumtazTsLrSegmentCvBa}% to {rqFiveMumtazTsLrSubjectCvBa}%",
        ),
        (
            "MODMA, frequency bands ({rqFiveModmaBpLrN})",
            "rqFiveModmaBpLrSegmentCvBa",
            "rqFiveModmaBpLrSubjectCvBa",
            "{rqFiveModmaBpLrSegmentCvBa}% to {rqFiveModmaBpLrSubjectCvBa}%",
        ),
        (
            "MODMA, sensor pairs ({rqFiveModmaTsLrN})",
            "rqFiveModmaTsLrSegmentCvBa",
            "rqFiveModmaTsLrSubjectCvBa",
            "{rqFiveModmaTsLrSegmentCvBa}% to {rqFiveModmaTsLrSubjectCvBa}%",
        ),
    ]
    x0, x1 = LEFT + 380, RIGHT - 190
    lo, hi = 40.0, 100.0

    def px(v: float) -> float:
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)

    y = BODY_Y
    for label, leaky, fair, values in rows:
        if leaky is None:
            d.text((LEFT, y + 6, 370, 28), label, size=18, bold=True, color="ink-3", into=g)
            y += 34
            continue
        d.text((LEFT, y, 370, 30), label, size=20, into=g)
        cy = y + 15
        d.line(x0, cy, x1, cy, "rule", 1, into=g)
        a, b = float(value_of(d.m[leaky])), float(value_of(d.m[fair]))
        d.line(px(b), cy, px(a), cy, "ink-3", 2.5, into=g)
        d.dot(px(a), cy, 7, "page", "ink-4", 2.5, into=g)
        d.dot(px(b), cy, 7, "ink", into=g)
        d.text((x1 + 16, y, 174, 30), values, size=20, align="r", into=g)
        y += 40
    for v in (40, 60, 80, 100):
        d.text(
            (px(v) - 30, y + 2, 60, 26),
            [[Span(f"{v}%", free=True)]],
            size=18,
            color="ink-3",
            align="c",
            into=g,
        )
    d.dot(LEFT + 6, y + 15, 7, "page", "ink-4", 2.5, into=g)
    d.text((LEFT + 20, y + 2, 150, 26), "leaky", size=18, color="ink-3", into=g)
    d.dot(LEFT + 106, y + 15, 7, "ink", into=g)
    d.text((LEFT + 120, y + 2, 200, 26), "fair", size=18, color="ink-3", into=g)
    rec.drawn.append(
        "Dumbbells drawn on the slide from the macros above, as docs/figures/web/elsewhere.png "
        "draws them."
    )


def backup_methods(d: Deck) -> None:
    rec = d.slide(
        "Backup  Calibration, method by method",
        "Methods that learned from other patients start higher; with enough practice the "
        "patient's own models catch up",
        0,
        "Three choices, first visit, all {rqTwoHTwoAN} patients. Solid lines learned from the "
        "other patients first, dashed ones from the new patient alone. The pre-trained EEGNet is "
        "best with no practice at all, {rqTwoRestAhSfEegnetEaFtKZeroMean}%, and the re-centred "
        "transfer is the pre-registered pair with the patient-only TS+LR. With all the practice, "
        "EEGNet from scratch reaches {rqTwoRestAhSfEegnetScratchKAllMean}%, CSP+LDA "
        "{rqTwoRestAhSfCspLdaKAllMean}%, the re-centred transfer {rqTwoRestAhSfRctTslrKAllMean}%.",
        tag="Pre-registered pair",
        part="backup",
    )
    g = d.group()
    ks = ["One", "Two", "Three", "Five", "Ten", "All"]
    minutes = [float(value_of(d.m[f"rqTwoMinutesK{k}"])) for k in ks]
    series = [
        ("Re-centred transfer", "RctTslr", "ink", 3.0, None, ks),
        ("EEGNet, pre-trained", "EegnetEaFt", "ink-3", 2.25, None, ks),
        ("TS+LR, patient only", "TsLr", "ink", 3.0, "dash", ks),
        ("CSP+LDA, patient only", "CspLda", "ink-3", 2.25, "dash", ks[1:]),
        ("EEGNet, from scratch", "EegnetScratch", "ink-4", 2.25, "dot", ks),
    ]
    x0, x1, y0, y1 = LEFT + 70, LEFT + 540, BODY_Y + 10, BODY_B - 56
    lo, hi = 35.0, 70.0

    def px(m: float) -> float:
        return x0 + m / 10 * (x1 - x0)

    def py(v: float) -> float:
        return y1 - (v - lo) / (hi - lo) * (y1 - y0)

    for v in (40, 50, 60, 70):
        d.line(x0, py(v), x1, py(v), "rule", 1, into=g)
        d.text(
            (x0 - 66, py(v) - 13, 58, 26),
            [[Span(f"{v}%", free=True)]],
            size=18,
            color="ink-3",
            align="r",
            into=g,
        )
    for m in (0, 2, 4, 6, 8, 10):
        d.text(
            (px(m) - 20, y1 + 6, 40, 26),
            [[Span(str(m), free=True)]],
            size=18,
            color="ink-3",
            align="c",
            into=g,
        )
    d.text(
        (x0, y1 + 30, x1 - x0, 26), "minutes of practice", size=18, color="ink-3", align="c", into=g
    )
    for _, method, colour, lw, dash, kk in series:
        pts = [
            (px(minutes[ks.index(k)]), py(float(value_of(d.m[f"rqTwoRestAhSf{method}K{k}Mean"]))))
            for k in kk
        ]
        d.path(pts, colour, lw, dash, into=g)
        for x, y in pts:
            d.dot(x, y, 4, "page", colour, 1.75, into=g)
    ly = BODY_Y + 40
    for name, _, colour, lw, dash, _ in series:
        d.line(x1 + 40, ly + 13, x1 + 84, ly + 13, colour, lw, dash, into=g)
        d.text((x1 + 94, ly, RIGHT - x1 - 94, 50), name, size=18, color="ink-2", into=g)
        ly += 56
    rec.drawn.append(
        "Lines drawn on the slide from the macros above (results/summary/calib_curves.csv), as "
        "docs/figures/rq2_calibration_curves.png plots them."
    )


def backup_healthy(d: Deck) -> None:
    rec = d.slide(
        "Backup  A benchmark in healthy people",
        "Two grasps of one hand are hard to tell apart even in {exThreeBenchPeople} healthy "
        "people: {exThreeBenchPairsMin} to {exThreeBenchPairsMax}% a week later",
        0,
        "From another public recording, {exThreeBenchPeople} healthy people imagined three grasps "
        "of the right hand on two days a week apart; we learned on day one and tested on day two. "
        "Any two grasps were told apart {exThreeBenchPairsMin} to {exThreeBenchPairsMax}% of the "
        "time, about guessing; one person would need "
        "{exThreeBenchCylindricalLumbricalCspLdaChance}% to beat chance. So telling two movements "
        "of one hand apart is hard in anyone, not a flaw of our model.",
        tag="Exploratory",
        part="backup",
    )
    g = d.group()
    rows = [
        ("Cylindrical or lumbrical", "CylindricalLumbrical"),
        ("Cylindrical or spherical", "CylindricalSpherical"),
        ("Spherical or lumbrical", "SphericalLumbrical"),
    ]
    x0, x1 = LEFT + 330, RIGHT - 20
    lo, hi = 40.0, 70.0

    def px(v: float) -> float:
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)

    top = BODY_Y + 30
    for i, (label, key) in enumerate(rows):
        y = top + i * 84
        d.text((LEFT, y, 320, 30), label, size=22, bold=True, into=g)
        d.line(x0, y + 15, x1, y + 15, "rule", 1, into=g)
        csp = float(value_of(d.m[f"exThreeBench{key}CspLdaMean"]))
        ts = float(value_of(d.m[f"exThreeBench{key}TsLrMean"]))
        d.dot(px(csp), y + 15, 8, "page", "ink-2", 2.5, into=g)
        d.dot(px(ts), y + 15, 8, "ink", into=g)
        d.text(
            (LEFT, y + 34, 320, 28),
            f"CSP+LDA {{exThreeBench{key}CspLdaMean}}%, TS+LR {{exThreeBench{key}TsLrMean}}%",
            size=18,
            color="ink-3",
            into=g,
        )
    gx = px(50)
    d.line(gx, top - 10, gx, top + 3 * 84 - 20, "ink-3", 1.25, dash="dash", into=g)
    d.text(
        (gx - 60, top + 3 * 84 - 16, 120, 26), "guessing", size=18, color="ink-3", align="c", into=g
    )
    for v in (40, 50, 60, 70):
        d.text(
            (px(v) - 30, top + 3 * 84 + 14, 60, 26),
            [[Span(f"{v}%", free=True)]],
            size=18,
            color="ink-3",
            align="c",
            into=g,
        )
    d.dot(LEFT + 6, 500, 7, "page", "ink-2", 2.5, into=g)
    d.text((LEFT + 20, 487, 120, 26), "CSP+LDA", size=18, color="ink-3", into=g)
    d.dot(LEFT + 136, 500, 7, "ink", into=g)
    d.text((LEFT + 150, 487, 200, 26), "TS+LR", size=18, color="ink-3", into=g)
    rec.drawn.append(
        "Dots drawn on the slide from the macros above "
        "(results/summary/ex3_grasp_pretraining_benchmark_summary.csv)."
    )


def backup_replay(d: Deck) -> None:
    rec = d.slide(
        "Backup  The replay as if live",
        "As if live, the methods catch {rqFourSwitchDetectMin} to {rqFourSwitchDetectMax}% of "
        "imagining, at {rqFourSwitchFalsePerMinMin} to {rqFourSwitchFalsePerMinMax} false starts "
        "a minute",
        0,
        "Runs 3 and 4 of each patient were played as one continuous signal; every half second the "
        "model read the newest four seconds, and a gate turned the finger on when the chance of a "
        "movement stayed above sixty percent twice in a row, off below forty-five percent "
        "(settings in configs/experiments/ex5_live_switch.yaml). A period counts as caught if the "
        "finger switches on during it. {rqFourReplayPeriods} periods were scored over "
        "{rqFourReplayRuns} runs. The demo's EEGNet catches the most but also makes the most "
        "mistakes; the central TS+LR switch, exploratory, makes about half as many.",
        tag="Exploratory",
        part="backup",
    )
    rec.drawn.append(REPLAY)
    g = d.group()
    points = [
        ("EEGNet, the demo's model", "rqFourSwitchEegnetScratch", "ink"),
        ("CSP+LDA", "rqFourSwitchCspLda", "ink-2"),
        ("Re-centred transfer", "rqFourSwitchRctTslr", "ink-2"),
        ("TS+LR", "rqFourSwitchTsLr", "ink-2"),
        ("TS+LR on the central sensors, exploratory", "exFiveMove", "sixth"),
    ]
    x0, x1, y0, y1 = LEFT + 80, LEFT + 500, BODY_Y + 36, BODY_B - 60
    xlo, xhi, ylo, yhi = 0.0, 1.5, 55.0, 70.0

    def px(v: float) -> float:
        return x0 + (v - xlo) / (xhi - xlo) * (x1 - x0)

    def py(v: float) -> float:
        return y1 - (v - ylo) / (yhi - ylo) * (y1 - y0)

    for v in (55, 60, 65, 70):
        d.line(x0, py(v), x1, py(v), "rule", 1, into=g)
        d.text(
            (x0 - 76, py(v) - 13, 66, 26),
            [[Span(f"{v}%", free=True)]],
            size=18,
            color="ink-3",
            align="r",
            into=g,
        )
    for v in (0.0, 0.5, 1.0, 1.5):
        d.text(
            (px(v) - 24, y1 + 6, 48, 26),
            [[Span(f"{v:g}", free=True)]],
            size=18,
            color="ink-3",
            align="c",
            into=g,
        )
    d.text(
        (x0, y1 + 32, x1 - x0, 26),
        "false switch-ons per minute of rest",
        size=18,
        color="ink-3",
        align="c",
        into=g,
    )
    d.text((x0 - 76, y0 - 38, 320, 26), "imagining periods caught", size=18, color="ink-3", into=g)
    lx, ly = x1 + 44, BODY_Y + 16
    for i, (name, stem, colour) in enumerate(points, start=1):
        fx = float(value_of(d.m[f"{stem}FalsePerMinMean"]))
        fy = float(value_of(d.m[f"{stem}DetectMean"]))
        number = [[Span(str(i), free=True)]]
        for cx, cy in ((px(fx), py(fy)), (lx + 13, ly + 15)):
            d.dot(cx, cy, 13, colour, into=g)
            d.text(
                (cx - 13, cy - 13, 26, 26),
                number,
                size=18,
                color="white",
                bold=True,
                align="c",
                anchor="m",
                into=g,
            )
        d.text(
            (lx + 38, ly, RIGHT - lx - 38, 70),
            [
                [Span(name, bold=True)],
                f"{{{stem}DetectMean}}% caught, {{{stem}FalsePerMinMean}} a minute",
            ],
            size=18,
            into=g,
        )
        ly += 74
    rec.drawn.append(
        "Points drawn on the slide from the macros above "
        "(results/summary/rq4_pseudo_online_switch_table.csv, ex5_live_switch_table.csv)."
    )


def backup_demo(d: Deck) -> None:
    d.slide(
        "Backup  The demo patient",
        "The demo patient was picked by a rule fixed in advance, as typical: {demoChosenByAcc}% "
        "against the group's median {demoCohortMedianAcc}%",
        0,
        "The demo plays one patient, {demoSubject}, chosen before the demo was built as the "
        "patient whose earlier score was closest to the group's median. On its {demoTrials} whole "
        "held-out trials the model is right {demoHeldOutAcc}% on three choices; rest is easy to "
        "spot and is half the windows, which lifts that score. It is one patient on few trials, "
        "so it wobbles: on every test window of the same runs it scores {demoWindowAcc}%. It is a "
        "different task from the {rqOneCspLdaCvLeakfreeMean}% for hand or sixth finger across "
        "{rqOneHOneN} patients.",
        part="backup",
    )
    g = d.group()
    tiles = [
        ("{demoHeldOutAcc}%", "three choices, on {demoTrials} trials it never saw"),
        ("{demoMoveRestAcc}%", "move or rest: {demoMoveRestRight} of {demoMoveRestN} right"),
        (
            "{demoHandFingerAcc}%",
            "hand or sixth finger: {demoHandFingerRight} of {demoHandFingerN} right",
        ),
        ("{demoTrainingTrials} trials", "all it learned from, this patient's runs 1 and 2"),
    ]
    tw, th = (BODY_W - 24) / 2, 160.0
    for i, (big, small) in enumerate(tiles):
        x = LEFT + (i % 2) * (tw + 24)
        y = BODY_Y + 10 + (i // 2) * (th + 24)
        d.box(x, y, tw, th, fill="white", line="rule", lw=1, radius=14, into=g)
        d.text((x + 24, y + 22, tw - 48, 50), big, size=36, bold=True, into=g)
        d.text((x + 24, y + 82, tw - 48, 60), small, size=20, color="ink-2", into=g)


def backup_trial(d: Deck) -> None:
    rec = d.slide(
        "Backup  One trial",
        "One trial as the patient saw it: rest, get ready, imagine; the model reads one piece of "
        "rest and one of imagining",
        0,
        "Each trial shows a cross for rest, a grey circle to get ready, then the picture of the "
        "hand or the sixth finger to imagine. The model reads two four-second pieces of each "
        "trial, one from rest and one from imagining, placed as the dataset paper places them. "
        "The demo's continuous mode reads the newest four seconds every half second instead.",
        tag="Descriptive",
        part="backup",
    )
    rec.drawn += [DESIGN, WINDOW]
    d.picture("trial", (LEFT, BODY_Y, BODY_W, BODY_H))


def backup_audit(d: Deck) -> None:
    d.slide(
        "Backup  Was the data sound?",
        "Before any test we compared every pair of the {nRuns} runs and set aside what was wrong "
        "in the shared recordings",
        0,
        "We gave each raw file a checksum and compared the signals of every pair of runs, "
        "{auditPairsScreened} pairs. Patient 2's after-therapy and follow-up sessions are the "
        "same files; patients 21 and 22 share one recording with different labels; one of patient "
        "15's runs lasts {auditDegenerateSeconds} seconds with no instruction in it. Every choice "
        "about the data was made before any accuracy was looked at; the full record is the data "
        "audit report in the repository.",
        part="backup",
    )
    g = d.group()
    rows = [
        (
            "Two sessions that are one recording",
            "Patient 2's after-therapy and follow-up files are identical",
            "kept one copy",
        ),
        (
            "Two patients with the same recording",
            "Patients 21 and 22, with different labels",
            "dropped both",
        ),
        (
            "A broken run",
            "Patient 15, one run of {auditDegenerateSeconds} s with no instruction",
            "dropped it",
        ),
    ]
    for i, (what, detail, did) in enumerate(rows):
        y = BODY_Y + 10 + i * 100
        d.dot(LEFT + 18, y + 18, 18, "page", "ink-2", 1.5, into=g)
        d.text(
            (LEFT, y + 4, 36, 28),
            [[Span(str(i + 1), free=True)]],
            size=18,
            align="c",
            anchor="m",
            into=g,
        )
        d.text((LEFT + 54, y, 560, 32), what, size=22, bold=True, into=g)
        d.text((LEFT + 54, y + 34, 560, 56), detail, size=20, color="ink-2", into=g)
        d.text((RIGHT - 230, y + 2, 230, 30), did, size=22, color="ink-2", align="r", into=g)
    d.text(
        (LEFT, 470, BODY_W, 50),
        "{auditPairsScreened} pairs of runs compared, every raw file checksummed, before any "
        "score was seen.",
        size=18,
        color="ink-3",
    )


TALK = [
    title_slide,
    problem_slide,
    bci_slide,
    rhythm_slide,
    data_slide,
    meaning_slide,
    leak_slide,
    fair_slide,
    methods_slide,
    headstart_slide,
    curve_slide,
    switch_slide,
    sure_slide,
    hand_too_slide,
    later_slide,
    live_slide,
    demo_slide,
    built_slide,
    added_slide,
    next_slide,
    close_slide,
]
BACKUP = [
    backup_leak,
    backup_elsewhere,
    backup_methods,
    backup_healthy,
    backup_replay,
    backup_demo,
    backup_trial,
    backup_audit,
]


# Output


def finish(prs: Presentation) -> bytes:
    """Save with fixed metadata and zip dates, so an unchanged deck is the same file."""
    cp = prs.core_properties
    cp.author = AUTHORS
    cp.last_modified_by = "Rajveer Singh"
    cp.title = "Sixth-Finger BCI"
    cp.subject = "EEG-based adaptive brain-computer interface for novel artificial limb control"
    cp.keywords = "EEG, motor imagery, stroke, brain-computer interface, sixth finger"
    cp.comments = ""
    cp.revision = 1
    cp.created = cp.modified = datetime(*STAMP)
    cp.last_printed = datetime(*STAMP)
    raw = io.BytesIO()
    prs.save(raw)
    out = io.BytesIO()
    with zipfile.ZipFile(raw) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = data.replace(b"On-screen Show (4:3)", b"Widescreen")
            zout.writestr(info, data)
    return out.getvalue()


def write_outline(d: Deck) -> None:
    lines = [
        "# The final presentation",
        "",
        "Written by `build_slides.py`; do not edit by hand. Every number in a headline is filled",
        "from `paper/generated/numbers.tex`. The talk is 15 minutes and the demo 3 more; the",
        "backup slides follow the closing slide. Figures are under `docs/figures/`; a cut one",
        "shows only its drawing, its words set on the slide.",
        "",
        "| # | Question | Headline | Figure | Time |",
        "|---|---|---|---|---|",
    ]
    for rec in d.records:
        files = []
        for key in rec.figures:
            fig = FIGS[key]
            name = f"`{fig.file}`" + (" (cut)" if fig.crop else "")
            if name not in files:
                files.append(name)
        figs = ", ".join(files) or "drawn on the slide"
        if rec.part == "backup":
            when = "backup"
        elif rec.part == "demo":
            when = f"{rec.seconds // 60}:{rec.seconds % 60:02d} demo"
        else:
            when = f"{rec.seconds // 60}:{rec.seconds % 60:02d}"
        ask = d.plain(rec.kicker, record=False) if rec.kicker else ""
        lines.append(f"| {rec.no} | {ask} | {rec.head} | {figs} | {when} |")
    OUTLINE.write_text("\n".join(lines) + "\n")


def export_pdf(pptx: Path) -> Path | None:
    """A PDF beside the deck, through LibreOffice or, on a Mac, Keynote; None if neither works."""
    pdf = pptx.with_suffix(".pdf")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    try:
        if soffice:
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(pptx.parent),
                    str(pptx),
                ],
                check=True,
                timeout=600,
            )
            return pdf
        if platform.system() == "Darwin" and Path("/Applications/Keynote.app").exists():
            script = (
                "on run argv\n"
                'tell application "Keynote"\n'
                "set doc to open POSIX file (item 1 of argv)\n"
                "export doc to POSIX file (item 2 of argv) as PDF with properties {PDF image "
                "quality:Best}\n"
                "close doc saving no\n"
                "end tell\n"
                "end run\n"
            )
            subprocess.run(
                ["osascript", "-e", script, str(pptx), str(pdf)], check=True, timeout=600
            )
            return pdf
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        print(f"no PDF: the converter failed ({err})", file=sys.stderr)
        return None
    print("no PDF: neither LibreOffice nor Keynote is on this machine", file=sys.stderr)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", action="store_true", help="also export a PDF beside the deck")
    args = parser.parse_args()

    load_colours()
    d = Deck(load_macros(), json.loads(PAGE_DATA.read_text()))
    for make in TALK + BACKUP:
        make(d)
    for rec in d.records:
        if rec.part == "backup":
            rec.seconds = 0
    d.notes()

    problems = d.check_text() + d.check_shapes() + d.check_figures()
    talk = sum(r.seconds for r in d.records if r.part not in ("demo", "backup"))
    if talk != TALK_SECONDS:
        problems.append(f"the talk comes to {talk} s, not {TALK_SECONDS}")
    blob = finish(d.prs)
    if len(blob) > MAX_BYTES:
        problems.append(f"the deck is {len(blob) / 1e6:.1f} MB, over 5 MB")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    OUT.write_bytes(blob)
    write_outline(d)
    main_count = sum(r.part != "backup" for r in d.records)
    print(
        f"wrote {OUT.relative_to(ROOT)}: {main_count} slides and "
        f"{len(d.records) - main_count} backups, {len(blob) / 1e6:.2f} MB, "
        f"talk {talk // 60}:{talk % 60:02d} + demo {DEMO_SECONDS // 60}:00"
    )
    if args.pdf:
        pdf = export_pdf(OUT)
        if pdf:
            print(f"wrote {pdf.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
