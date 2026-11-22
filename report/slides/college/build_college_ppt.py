"""Build the final presentation in the college's template, Sixth-Finger-BCI-Final-PPT.pptx.

uv run --with python-pptx==1.0.2 python report/slides/college/build_college_ppt.py
uv run --with python-pptx==1.0.2 python report/slides/college/build_college_ppt.py --pdf --previews

The deck starts from a copy of the college's "Final PPT.pptx", so its master, layouts, logo,
background, arrow and title placement are the template's own, and keeps its order: title,
contents, introduction, proposed solution, dataset, experimental details, results, conclusion,
questions, thank you. Type is Georgia for titles and Arial for the rest, both on every Windows
PC; colour is the template's blue and navy with the MSIT logo's red and gold. Numbers come from
paper/generated/numbers.tex through the macros of ../build_slides.py, written in the slide text
as {macroName}; the speaker notes give each one with its results file. The build fails on text
under 16 pt, text that does not fit its box, a figure whose smallest text would print under
16 pt, a digit typed by hand, or a talk that is not 15:00.

The deck carries the students' enrolment numbers: it is not copied to the website.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from lxml import etree
from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Pt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_slides as bs  # noqa: E402

ROOT = bs.ROOT
OUT = HERE / "Sixth-Finger-BCI-Final-PPT.pptx"
PREVIEWS = HERE / "previews"
TEMPLATE = Path.home() / "Downloads" / "Final PPT.pptx"
SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
SUPPLEMENTAL = Path("/System/Library/Fonts/Supplemental")

# The template's slide in points. Content starts where the title's text starts and keeps clear
# of the curves on the left.
W, H = 960.0, 540.0
CL, CR = 212.0, 924.0
CW = CR - CL
CT = 120.0
TITLE_BOX = (204.2, 40.0, 701.7, 62.0)
MIN_PT = 16.0
TALK_SECONDS = 15 * 60
DEMO_SECONDS = 3 * 60
MAX_BYTES = 5_000_000

# Type: Georgia for titles, Arial for everything else; both ship with Windows and macOS.
SERIF, SANS = "Georgia", "Arial"
TITLE_PT = 32.0
LEAD_PT = 22.0
BODY_PT = 20.0
SMALL_PT = 18.0
CAPTION_PT = 16.0
STAT_PT = 36.0
PDF_FONTS = ("ArialMT", "Arial-Bold", "Arial-Italic", "Georgia", "Wingdings3")

# Colour: the template's navy (its dk2) and a deeper cut of its title blue, the MSIT logo's red
# and gold, on calm inks. Every text colour keeps 4.5:1 on the darkest part of the background.
PALETTE = {
    "ink": "1D2A33",
    "navy": "2E5369",
    "blue": "105C82",
    "red": "A93220",
    "gold": "E9B520",
    "cream": "FFF6DA",
    "muted": "4A5D68",
    "line": "B9CDD6",
    "pale": "EAF3F6",
    "white": "FFFFFF",
}

STUDENTS = [
    ("Rajveer Singh", "05096302823"),
    ("Vivek Yadav", "05196302823"),
    ("Ansh Dahiya", "35396302823"),
]
GUIDE = ["Dr. Suman Lata", "Assistant Professor", "Department of ECE, MSIT"]
TOPIC = "EEG-Based Adaptive Brain–Computer Interface for Novel Artificial Limb Control"
SITE = "sixth-finger-bci.vercel.app"
SITE_COPY = "sixthfinger.rajveers.com"
STAMP = (2026, 11, 22, 0, 0, 0)

# Digits a slide may carry without a macro: years, run, session and hypothesis names, patient
# codes, the licence, named datasets.
FREE_DIGITS = re.compile(
    r"\b(?:19|20)\d\d\b|\bruns? \d(?:[–-]\d)?\b|\bsub-\d+\b|\bH\d[abc]?\b|CC BY 4\.0"
    r"|BNCI 2014-001|Track 4|\bk = \d\b",
)
# Words the revised paper dropped, so the deck may not bring them back.
BANNED = re.compile(r"\bfair(?:ly)?\b|overtak|works best", re.IGNORECASE)


def rgb(name: str) -> RGBColor:
    return RGBColor.from_string(PALETTE[name])


# Text measurement with the deck's own fonts


FONT_FILES = {
    SANS: ("Arial", "Arial Bold", "Arial Italic", "Arial Bold Italic"),
    SERIF: ("Georgia", "Georgia Bold", "Georgia Italic", "Georgia Bold Italic"),
}


class Measure:
    """Widths and line height of Arial and Georgia, read from the font files."""

    def __init__(self) -> None:
        self.fonts = {}
        heights = []
        for family, files in FONT_FILES.items():
            for (bold, italic), name in zip(
                [(False, False), (True, False), (False, True), (True, True)], files, strict=True
            ):
                font = ImageFont.truetype(str(SUPPLEMENTAL / f"{name}.ttf"), 1000)
                self.fonts[(family == SERIF, bold, italic)] = font
            ascent, descent = self.fonts[(family == SERIF, False, False)].getmetrics()
            heights.append((ascent + descent) / 1000)
        # PowerPoint sets single spacing at about 1.2 of the size for these fonts, a little more
        # than LibreOffice; the larger keeps both inside their boxes.
        self.line = max(1.2, max(heights) * 1.04)

    def width(self, text: str, size: float, bold: bool, italic: bool = False, serif=False) -> float:
        return self.fonts[(serif, bold, italic)].getlength(text) * size / 1000

    def lines(self, spans: list[bs.Span], width: float, size: float) -> int:
        words: list[tuple[str, float, bool, bool, bool]] = []
        for sp in spans:
            sz = (sp.size or size) * (0.6 if sp.sup else 1)
            for word in re.split(r"(\s+)", sp.text):
                if word:
                    words.append((word, sz, bool(sp.bold), sp.italic, sp.serif))
        lines, used = 1, 0.0
        # A point of slack for kerning and hinting differences between renderers.
        room = width - 1
        for word, sz, b, i, s in words:
            w = self.width(word, sz, b, i, s)
            if word.isspace():
                used += w
                continue
            if w > room:
                # A word wider than the box breaks inside itself; count it as never fitting.
                lines += 99
            if used and used + w > room:
                lines += 1
                used = w
            else:
                used += w
        return lines


# Figures


@dataclass(frozen=True)
class Fig:
    file: str
    shows: str
    crop: tuple[int, int, int, int] | None = None
    px_per_css: int = 3
    small: float | None = None
    checks: tuple[tuple[str, str, int], ...] = ()
    # The drawing's paper, when it is not pure white (the hand pictures sit on 250 grey).
    paper: int = 255


def from_deck(key: str) -> Fig:
    f = bs.FIGS[key]
    return Fig(f.file, f.shows, f.crop, f.px_per_css, f.small, f.checks)


FIGS: dict[str, Fig] = {
    key: from_deck(key)
    for key in [
        "hand-rest",
        "hand-finger",
        "system",
        "leak",
        "leak-slope",
        "setup",
        "switch-patients",
        "path-cap",
        "path-practice",
        "path-therapy",
    ]
}
for _key in ("hand-rest", "hand-finger"):
    FIGS[_key] = replace(FIGS[_key], paper=250)
FIGS["model"] = Fig(
    "web/model.png",
    "EEGNet as five stations: the signal in, rhythms, sensors, combining, the three lamps",
    (30, 120, 2320, 415),
)


def figure_png(fig: Fig) -> tuple[bytes, int, int]:
    """The figure cropped, with its paper taken out so it sits on any frame."""
    im = Image.open(bs.FIGURES / fig.file)
    if im.mode == "RGBA":
        white = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(white, im)
    im = im.convert("RGB")
    if fig.crop:
        im = im.crop(fig.crop)
    rgb_ = np.clip(np.asarray(im).astype(np.float64) / fig.paper, 0, 1)
    # Undo "drawn over white": the least alpha that explains each pixel, and its colour.
    alpha = 1 - rgb_.min(axis=2)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    colour = np.clip((rgb_ - (1 - alpha[..., None])) / safe, 0, 1)
    rgba = np.dstack([colour, alpha])
    out = Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA")
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue(), out.width, out.height


# The deck


@dataclass
class TextBox:
    slide: int
    paras: list[list[bs.Span]]
    size: float
    w: float
    h: float
    gap: float
    first_gap: bool = False


@dataclass
class Record:
    no: int
    slide: Any
    title: str
    seconds: int
    part: str = "talk"
    say: str = ""
    numbers: list[tuple[str, str]] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    settings: list[str] = field(default_factory=list)
    drawn: list[str] = field(default_factory=list)
    has_free: bool = False
    lists: int = 0
    blank: Any = None


class Deck:
    def __init__(self, template: Path, macros: dict[str, bs.Macro], data: dict) -> None:
        self.prs = Presentation(str(template))
        self.m = macros
        self.data = data
        self.measure = Measure()
        self.records: list[Record] = []
        self.boxes: list[TextBox] = []
        self.rec: Record | None = None
        self.template = list(self.prs.slides)
        self.layout = self.prs.slide_layouts.get_by_name("Title and Content")
        self.theme_fonts()

    def theme_fonts(self) -> None:
        """The theme's heading and body fonts, for anything that falls back to them."""
        part = self.prs.slide_master.part.part_related_by(RT.THEME)
        xml = part.blob.decode("utf-8")
        for kind, face in (("majorFont", SERIF), ("minorFont", SANS)):
            xml = re.sub(
                rf"(<a:{kind}><a:latin typeface=\")[^\"]*(\")[^/]*/>",
                rf"\g<1>{face}\g<2>/>",
                xml,
            )
        part._blob = xml.encode("utf-8")

    # Text templates: {macro} or {macro:fmt} is a number, **...** bold, <<...>> a setting.

    def fill(self, template: str, record: bool = True, **style: Any) -> list[bs.Span]:
        out: list[bs.Span] = []
        pos = 0
        for m in bs.PLACEHOLDER.finditer(template):
            if m.start() > pos:
                out.append(bs.Span(template[pos : m.start()], **style))
            macro = self.m[m.group(1)]
            shown = bs.show(macro, m.group(2) or "")
            for sp in shown:
                for k, v in style.items():
                    setattr(sp, k, v)
                out.append(sp)
            if record and self.rec is not None:
                text = "".join(f"^{sp.text}" if sp.sup else sp.text for sp in shown)
                self.rec.numbers.append((macro.name, text))
            pos = m.end()
        if pos < len(template):
            out.append(bs.Span(template[pos:], **style))
        return out

    def rich(self, template: str, record: bool = True, bold: bool = False, **style: Any) -> list:
        spans: list[bs.Span] = []
        for i, part in enumerate(template.split("**")):
            for j, piece in enumerate(re.split(r"<<|>>", part)):
                if not piece:
                    continue
                free = j % 2 == 1
                if free and self.rec is not None:
                    self.rec.has_free = True
                spans += self.fill(piece, record, bold=bold or i % 2 == 1, free=free, **style)
        return spans

    def plain(self, template: str, record: bool = True) -> str:
        spans = self.rich(template, record)
        return "".join(f"^{sp.text}" if sp.sup else sp.text for sp in spans)

    def _runs(
        self, p: Any, spans: list[bs.Span], size: float, color: str, nums: str | None = None
    ) -> None:
        if nums:
            # A per cent sign right after a number takes the number's colour.
            split: list[bs.Span] = []
            for sp in spans:
                if split and split[-1].macro and not sp.macro and sp.text.startswith("%"):
                    split.append(replace(sp, text="%", macro=split[-1].macro, free=True))
                    sp = replace(sp, text=sp.text[1:])
                if sp.text:
                    split.append(sp)
            spans = split
        for sp in spans:
            r = p.add_run()
            r.text = sp.text
            f = r.font
            f.name = SERIF if sp.serif else SANS
            f.size = Pt(sp.size or size)
            f.bold = bool(sp.bold) or bool(nums and sp.macro)
            f.italic = sp.italic
            f.color.rgb = rgb(sp.color or (nums if nums and sp.macro else color))
            if sp.sup:
                f._rPr.set("baseline", "30000")

    def _paras(self, paras: list[str | list[bs.Span]], bold: bool, **style: Any) -> list:
        return [p if isinstance(p, list) else self.rich(p, bold=bold, **style) for p in paras]

    def height(self, paras: list[list[bs.Span]], width: float, size: float, gap: float) -> float:
        total = 0.0
        for i, p in enumerate(paras):
            if not p:
                continue
            biggest = max(sp.size or size for sp in p)
            total += self.measure.lines(p, width, size) * biggest * self.measure.line
            if i:
                total += gap
        return total

    def text(
        self,
        box: tuple[float, float, float, float],
        paras: str | list[str | list[bs.Span]],
        size: float = BODY_PT,
        bold: bool = False,
        color: str = "ink",
        align: str = "l",
        anchor: str = "t",
        gap: float = 0,
        italic: bool = False,
        serif: bool = False,
        nums: str | None = None,
    ) -> Any:
        """A text box without insets; nums colours (and bolds) the macro numbers in it."""
        x, y, w, h = box
        if isinstance(paras, str):
            paras = [paras]
        resolved = self._paras(paras, bold, italic=italic, serif=serif)
        shape = self.rec.slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
        tf = shape.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, side, 0)
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[
            anchor
        ]
        for i, spans in enumerate(resolved):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
            p.line_spacing = 1.0
            p.space_before = Pt(gap if i else 0)
            p.space_after = Pt(0)
            self._runs(p, spans, size, color, nums)
        self.boxes.append(TextBox(self.rec.no, resolved, size, w, h, gap))
        return shape

    def bullets(
        self,
        box: tuple[float, float, float, float],
        items: list[str],
        size: float = BODY_PT,
        gap: float = 10,
        color: str = "ink",
        nums: str | None = "blue",
        mark: str = "blue",
    ) -> Any:
        """Bullets in the template's own body placeholder, with its arrow bullets.

        The box is where the bullet arrow starts; the text hangs 27 pt to its right.
        """
        x, y, w, h = box
        ph = self._body()
        # Above any card already on the slide.
        tree = ph._element.getparent()
        tree.remove(ph._element)
        tree.append(ph._element)
        # Placeholder insets: 7.2 pt a side, 3.6 top and bottom.
        ph.left, ph.top, ph.width, ph.height = Pt(x - 7.2), Pt(y - 3.6), Pt(w + 7.2), Pt(h + 3.6)
        tf = ph.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.text = ""
        resolved = self._paras(items, False)
        for i, spans in enumerate(resolved):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(gap if i else 0)
            p.line_spacing = 1.0
            self._runs(p, spans, size, color, nums)
            ppr = p._p.get_or_add_pPr()
            clr = etree.SubElement(ppr, qn("a:buClr"))
            etree.SubElement(clr, qn("a:srgbClr"), val=PALETTE[mark])
            etree.SubElement(ppr, qn("a:buSzPct"), val="85000")
        self.boxes.append(TextBox(self.rec.no, resolved, size, w - 7.2 - 27, h - 3.6, gap))
        return ph

    def _body(self) -> Any:
        """The body placeholder; a second list on a slide gets a copy of it."""
        found = [s for s in self.rec.slide.placeholders if s.placeholder_format.idx == 1]
        if not found:
            raise ValueError(f"slide {self.rec.no} has no body placeholder")
        self.rec.lists += 1
        if self.rec.lists == 1:
            self.rec.blank = copy.deepcopy(found[0]._element)
            return found[0]
        el = copy.deepcopy(self.rec.blank)
        tree = self.rec.slide.shapes._spTree
        el.find(qn("p:nvSpPr")).find(qn("p:cNvPr")).set(
            "id", str(max(int(e.get("id")) for e in tree.iter(qn("p:cNvPr"))) + 1)
        )
        tree.append(el)
        return next(s for s in self.rec.slide.shapes if s._element is el)

    def drop_body(self) -> None:
        for shape in list(self.rec.slide.placeholders):
            if shape.placeholder_format.idx == 1:
                shape._element.getparent().remove(shape._element)

    # Slides

    def slide(
        self,
        title: str,
        seconds: int,
        say: str,
        part: str = "talk",
        reuse: int | None = None,
    ) -> Record:
        """A content slide: one of the template's own, or a new one from its layout."""
        s = self.template[reuse] if reuse is not None else self.prs.slides.add_slide(self.layout)
        rec = Record(len(self.records) + 1, s, "", seconds, part)
        self.records.append(rec)
        self.rec = rec
        if title:
            t = s.shapes.title
            x, y, w, h = TITLE_BOX
            t.left, t.top, t.width, t.height = Pt(x), Pt(y), Pt(w), Pt(h)
            tf = t.text_frame
            tf.auto_size = MSO_AUTO_SIZE.NONE
            tf.text = ""
            spans = self.rich(title, bold=True, serif=True)
            p = tf.paragraphs[0]
            for sp in spans:
                r = p.add_run()
                r.text = sp.text
                r.font.name = SERIF
                r.font.bold = True
                r.font.size = Pt(TITLE_PT)
            self.boxes.append(TextBox(rec.no, [spans], TITLE_PT, w - 14.4, h - 7.2, 0))
            rec.title = "".join(sp.text for sp in spans)
        else:
            rec.title = s.shapes.title.text_frame.text
        rec.say = self.plain(say)
        return rec

    def keep(self, index: int, seconds: int, say: str, part: str = "talk") -> Record:
        """One of the template's slides as it is, with notes only."""
        return self.slide("", seconds, say, part, reuse=index)

    # Shapes

    @staticmethod
    def _plain(shape: Any) -> None:
        style = shape._element.find(qn("p:style"))
        if style is not None:
            shape._element.remove(style)

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str | None = "white",
        line: str | None = "line",
        lw: float = 0.75,
        dash: bool = False,
        radius: float = 6,
        oval: bool = False,
    ) -> Any:
        kind = (
            MSO_SHAPE.OVAL
            if oval
            else (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
        )
        shape = self.rec.slide.shapes.add_shape(kind, Pt(x), Pt(y), Pt(w), Pt(h))
        self._plain(shape)
        if radius and not oval:
            shape.adjustments[0] = min(0.5, radius / min(w, h))
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = rgb(fill)
        else:
            shape.fill.background()
        if line:
            shape.line.color.rgb = rgb(line)
            shape.line.width = Pt(lw)
            if dash:
                shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        else:
            shape.line.fill.background()
        return shape

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "navy",
        lw: float = 1.5,
        arrow: bool = False,
        dash: bool = False,
    ) -> Any:
        c = self.rec.slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Pt(x1), Pt(y1), Pt(x2), Pt(y2)
        )
        self._plain(c)
        c.line.color.rgb = rgb(color)
        c.line.width = Pt(lw)
        if dash:
            c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if arrow:
            ln = c.line._get_or_add_ln()
            etree.SubElement(ln, qn("a:tailEnd"), type="triangle", w="med", len="med")
        return c

    def badge(self, cx: float, cy: float, label: str, r: float = 12, fill: str = "navy") -> None:
        """A numbered circle, as the flowchart and the lists use."""
        self.box(cx - r, cy - r, 2 * r, 2 * r, fill=fill, line=None, oval=True)
        self.text(
            (cx - r, cy - r, 2 * r, 2 * r),
            [[bs.Span(label, bold=True, free=True)]],
            size=CAPTION_PT,
            color="white",
            align="c",
            anchor="m",
        )

    def band(
        self,
        box: tuple[float, float, float, float],
        paras: str | list[str | list[bs.Span]],
        size: float = SMALL_PT,
        nums: str | None = "blue",
        gap: float = 4,
    ) -> None:
        """The takeaway: a cream band with a gold edge, from the logo's yellow."""
        x, y, w, h = box
        self.box(x, y, w, h, fill="cream", line=None, radius=4)
        self.box(x, y, 5, h, fill="gold", line=None, radius=0)
        self.text((x + 18, y + 6, w - 30, h - 12), paras, size=size, anchor="m", nums=nums, gap=gap)

    def picture(
        self, key: str, box: tuple[float, float, float, float], align: str = "c", valign: str = "m"
    ) -> tuple[float, float, float, float]:
        """A figure as large as the box allows; fails if its smallest text prints too small."""
        x, y, w, h = box
        fig = FIGS[key]
        blob, pw, ph = figure_png(fig)
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

    def framed(
        self,
        key: str,
        box: tuple[float, float, float, float],
        pad: float = 8,
        below: float = 0,
        align: str = "l",
        valign: str = "t",
        line: str = "line",
        lw: float = 0.75,
        dash: bool = False,
        wide: bool = False,
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
        """A figure on a white card, the card fitted to it (or as wide as the box, if wide);
        below leaves room for a caption.

        Returns the picture's box and the card's box.
        """
        x, y, w, h = box
        fig = FIGS[key]
        _, pw, ph = figure_png(fig)
        scale = min((w - 2 * pad) / pw, (h - 2 * pad - below) / ph)
        cw, ch = pw * scale + 2 * pad, ph * scale + 2 * pad + below
        if wide:
            cw = w
        cx = x + {"l": 0, "c": (w - cw) / 2, "r": w - cw}[align]
        cy = y + {"t": 0, "m": (h - ch) / 2, "b": h - ch}[valign]
        self.box(cx, cy, cw, ch, fill="white", line=line, lw=lw, dash=dash)
        pic = self.picture(key, (cx + pad, cy + pad, cw - 2 * pad, ch - 2 * pad - below))
        return pic, (cx, cy, cw, ch)

    def number_slide(self, rec: Record) -> None:
        """The slide number in the template's own place, on the dark arrow."""
        ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
        a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        tree = rec.slide.shapes._spTree
        new_id = max(int(e.get("id")) for e in tree.iter(qn("p:cNvPr"))) + 1
        sp = etree.fromstring(
            f'<p:sp xmlns:p="{ns}" xmlns:a="{a}"><p:nvSpPr>'
            f'<p:cNvPr id="{new_id}" name="Slide Number"/><p:cNvSpPr>'
            '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldNum" sz="quarter" '
            'idx="12"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>'
            '<a:fld id="{69E57DC2-970A-4B3E-BB1C-7A09969E49DF}" type="slidenum">'
            f'<a:rPr lang="en-US" sz="1800" b="1"><a:latin typeface="{SANS}"/></a:rPr>'
            f"<a:t>{rec.no}</a:t></a:fld></a:p></p:txBody></p:sp>"
        )
        tree.append(sp)

    def retype(self) -> None:
        """The template's own runs in the deck's fonts: Georgia in titles, Arial elsewhere."""
        old = {"Times New Roman", "Franklin Gothic Book"}
        for rec in self.records:
            for shape in rec.slide.shapes:
                if not shape.has_text_frame:
                    continue
                is_title = shape.is_placeholder and shape.placeholder_format.type in (1, 3)
                face = SERIF if is_title else SANS
                for tag in ("a:latin", "a:ea", "a:cs", "a:buFont"):
                    for el in shape._element.iter(qn(tag)):
                        if el.get("typeface") in old:
                            el.set("typeface", face)

    # Checks

    def check_text(self) -> list[str]:
        problems = []
        for b in self.boxes:
            sizes = [sp.size or b.size for p in b.paras for sp in p if not sp.sup]
            if sizes and min(sizes) < MIN_PT:
                problems.append(f"slide {b.slide}: text at {min(sizes)} pt")
            height = self.height(b.paras, b.w, b.size, b.gap)
            if height > b.h + 1:
                text = "".join(sp.text for p in b.paras for sp in p)[:60]
                problems.append(f"slide {b.slide}: '{text}' needs {height:.0f} pt, has {b.h:.0f}")
            for p in b.paras:
                for sp in p:
                    if BANNED.search(sp.text):
                        problems.append(f"slide {b.slide}: '{sp.text}' uses a dropped word")
                    if sp.macro or sp.free:
                        continue
                    if re.search(r"\d", FREE_DIGITS.sub("", sp.text)):
                        problems.append(f"slide {b.slide}: a digit typed by hand in '{sp.text}'")
        for rec in self.records:
            if rec.has_free and not rec.settings:
                problems.append(f"slide {rec.no}: a setting on the slide without its source")
            if BANNED.search(rec.say):
                problems.append(f"slide {rec.no}: the notes use a dropped word")
        return problems

    def check_shapes(self) -> list[str]:
        problems = []
        for rec in self.records:
            for shape in rec.slide.shapes:
                if shape.left is None:
                    continue
                x, y = shape.left / 12700, shape.top / 12700
                right, bottom = x + shape.width / 12700, y + shape.height / 12700
                if x < -0.5 or y < -0.5 or right > W + 0.5 or bottom > H + 0.5:
                    problems.append(f"slide {rec.no}: '{shape.name}' leaves the slide")
        return problems

    def check_figures(self) -> list[str]:
        problems = []
        for key in sorted({k for r in self.records for k in r.figures}):
            for name, path, factor in FIGS[key].checks:
                value = bs.value_of(self.m[name])
                exponent = value.as_tuple().exponent
                places = -exponent if isinstance(exponent, int) else 0
                tolerance = Decimal(5).scaleb(-places - 1) + Decimal("1e-9")
                shown = Decimal(str(bs.data_at(self.data, path))) * factor
                if abs(shown - value) > tolerance:
                    problems.append(f"{key}: data.json {path} = {shown} but \\{name} = {value}")
        return problems

    # Notes

    def notes(self) -> None:
        talk = 0
        for rec in self.records:
            if rec.part == "demo":
                lines = [
                    f"Demo: {rec.seconds // 60}:{rec.seconds % 60:02d}, not part of the 15:00."
                ]
            elif rec.part == "questions":
                lines = ["Questions: after the talk and the demo, not timed."]
            else:
                talk += rec.seconds
                lines = [
                    f"Time: {rec.seconds // 60}:{rec.seconds % 60:02d} "
                    f"(by the end of this slide {talk // 60}:{talk % 60:02d} of 15:00)."
                ]
            lines += ["", "Say: " + rec.say]
            if rec.numbers:
                lines += ["", "Numbers, from paper/generated/numbers.tex:"]
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
                if fig.checks:
                    names = ", ".join(sorted({f"\\{n}" for n, _, _ in fig.checks}))
                    lines.append(
                        "Its printed values come from web/src/explain/data.json "
                        f"(scripts/make_web_explain_data.py) and equal {names}, checked at build."
                    )
            for what in rec.settings + rec.drawn:
                lines += ["", what]
            rec.slide.notes_slide.notes_text_frame.text = "\n".join(lines)


# Settings and design facts said on slides, with the file that fixes each.

WINDOW = (
    "Settings, not results: each reading is a 4 s window, 1 to 5 s after the cue "
    "(configs/data.yaml)."
)
DESIGN = (
    "The study's design, not results (docs/dataset-card.md, from Wang et al., 2026): sessions "
    "before two weeks of therapy, after it and a month later; 4 runs of 20 trials a session; "
    "40 analysed channels (configs/data.yaml, channels)."
)
CENTRAL = (
    "Setting, not a result: the switch reads the 14 channels over the movement area "
    "(configs/experiments/ex4_sf_command.yaml)."
)
REPLAY = (
    "Settings, not results: continuous replay reads a 4 s window every 0.5 s through the "
    "demonstrator's gate (configs/experiments/ex5_live_switch.yaml)."
)
STAGES = "The numbers 1 to 8 in the flowchart are its stages, as in report/figures/approach.tex."


# The talk. Times in seconds; the talk comes to 15:00, the demo is apart.


def title_slide(d: Deck) -> None:
    rec = d.keep(
        0,
        30,
        "Good morning. We are Rajveer Singh, Vivek Yadav and Ansh Dahiya, and our minor project, "
        "guided by Dr. Suman Lata, asks whether a stroke patient's brain signals can control a "
        "robotic sixth finger, and how quickly such a system can be set up for a new patient.",
    )
    s = rec.slide
    shapes = list(s.shapes)
    heading, by_hand, topic, guide = shapes[0], shapes[1], shapes[2], shapes[3]

    def refill(shape: Any, paras: list[list[bs.Span]], gap: float = 0) -> None:
        tf = shape.text_frame
        tf.auto_size = MSO_AUTO_SIZE.NONE
        body = tf._txBody.find(qn("a:bodyPr"))
        for fit in body.findall(qn("a:normAutofit")):
            body.remove(fit)
        tf.text = ""
        for i, spans in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(gap if i else 0)
            p.line_spacing = 1.0
            for sp in spans:
                r = p.add_run()
                r.text = sp.text
                r.font.name = SERIF if sp.serif else SANS
                r.font.bold = bool(sp.bold)
                r.font.size = Pt(sp.size)
                r.font.color.rgb = rgb(sp.color)
        w, h = shape.width / 12700, shape.height / 12700
        d.boxes.append(TextBox(rec.no, paras, paras[-1][0].size, w - 14.4, h - 7.2, gap))

    refill(
        heading,
        [[bs.Span("Minor Project presentation", bold=True, serif=True, size=30, color="blue")]],
    )
    heading.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    refill(topic, [[bs.Span(TOPIC, bold=True, serif=True, size=28, color="navy")]])
    topic.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    topic.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

    # A short gold rule between the topic and the people, from the logo's yellow.
    mid = topic.left / 12700 + topic.width / 12700 / 2
    rule_y = topic.top / 12700 + topic.height / 12700 + 8
    d.box(mid - 40, rule_y, 80, 3.5, fill="gold", line=None, radius=0)

    top = rule_y + 22
    for shape in (by_hand, guide):
        shape.top = Pt(top)
        shape.height = Pt(150)
    label = {"bold": True, "size": CAPTION_PT, "color": "muted"}
    names = [[bs.Span("By:", **label)]] + [
        [
            bs.Span(name, bold=True, size=BODY_PT, color="ink"),
            bs.Span(f"  ({number})", size=SMALL_PT, color="muted", free=True),
        ]
        for name, number in STUDENTS
    ]
    refill(by_hand, names, gap=6)
    guide.left = Pt(612)
    guide.width = Pt(W - 24 - 612)
    paras = [[bs.Span("Under the guidance of:", **label)]]
    paras.append([bs.Span(GUIDE[0], bold=True, size=BODY_PT, color="ink")])
    paras += [[bs.Span(line, size=SMALL_PT, color="ink")] for line in GUIDE[1:]]
    refill(guide, paras, gap=6)
    for shape in (by_hand, guide):
        for p in shape.text_frame.paragraphs:
            p.alignment = PP_ALIGN.LEFT
    rec.drawn.append(
        "The enrolment numbers on this slide are why this deck never goes on the website."
    )


def contents_slide(d: Deck) -> None:
    rec = d.keep(
        1,
        10,
        "The talk follows the college's order: why the problem matters, what we did, the data, "
        "how we did it, what we found, and what it means; the live demo comes just before "
        "questions.",
    )
    body = next(s for s in rec.slide.placeholders if s.placeholder_format.idx == 1)
    items = [p.text.strip() for p in body.text_frame.paragraphs if p.text.strip()]
    d.bullets((CL, CT + 6, 520, 380), items, size=LEAD_PT, gap=14, color="navy")


def background_slide(d: Deck) -> None:
    d.slide(
        "Introduction: background",
        60,
        "After a stroke one hand often stays too weak to grip a cup or a bag. A robotic sixth "
        "finger worn on that wrist can press things against the palm, so the hand holds them "
        "again. We want the patient to control it by imagining the movement, with no button to "
        "press.",
        reuse=2,
    )
    d.bullets(
        (CL, CT + 44, 300, 300),
        [
            "**Stroke** often leaves one hand too weak to grip",
            "A **robotic sixth finger**, worn on that wrist, grips against the palm",
            "Aim: the patient **imagines** moving it, and it moves",
        ],
        size=LEAD_PT,
        gap=20,
    )
    cw, gap = 190.0, 16.0
    x0 = CR - 2 * cw - gap
    for i, (key, label) in enumerate([("hand-rest", "at rest"), ("hand-finger", "bent to grip")]):
        x = x0 + i * (cw + gap)
        _, (_, cy, _, ch) = d.framed(key, (x, CT + 14, cw, 330), pad=12, below=30)
        d.text((x, cy + ch - 32, cw, 22), label, size=SMALL_PT, align="c", color="muted")
    d.line(CL, 462, CR, 462, color="line", lw=0.75)
    d.text(
        (CL, 472, CW, 44),
        [
            "BCI therapy after stroke: Cervera et al., 2018. Extra robotic fingers: "
            "Prattichizzo et al., 2021; Kieliba et al., 2021."
        ],
        size=CAPTION_PT,
        color="muted",
    )


def bci_slide(d: Deck) -> None:
    rec = d.slide(
        "Introduction: what a BCI is",
        45,
        "A brain–computer interface turns brain signals into a command without the body moving. "
        "The EEG cap picks up tiny voltages, the amplifier passes a few seconds at a time to the "
        "model, and the model answers rest, hand or sixth finger; on sixth finger the finger "
        "bends. It recognises a trained pattern, a weakening of the mu rhythm over the motor "
        "area; it does not read thoughts.",
    )
    rec.settings.append(WINDOW)
    (x, y, w, _), (cx0, cy, cw0, ch) = d.framed(
        "system", (CL, CT - 4, CW, 312), pad=12, below=40, wide=True
    )
    crop = FIGS["system"].crop or (0, 0, 0, 0)
    k = w / (crop[2] - crop[0])
    # The drawing's own numbers print small; larger ones are laid over them.
    centres = [(461, 382), (741, 434), (1039, 489), (1609.5, 593), (1820.5, 631)]
    for i, (cx, cyy) in enumerate(centres, start=1):
        d.badge(x + (cx - crop[0]) * k, y + (cyy - crop[1]) * k, str(i), r=13)
    names = ["EEG cap", "Amplifier", "<<4 s>> of signal", "Model", "Robotic finger"]
    colw = (cw0 - 16) / len(names)
    for i, name in enumerate(names, start=1):
        spans = [bs.Span(f"{i}  ", bold=True, free=True, color="blue"), *d.rich(name)]
        d.text(
            (cx0 + 8 + (i - 1) * colw, cy + ch - 34, colw, 24), [spans], size=SMALL_PT, align="c"
        )
    d.band(
        (CL, cy + ch + 14, CW, 516 - cy - ch - 14),
        "It spots a trained pattern: imagining a movement weakens the **mu rhythm** over the "
        "motor area. It does not read thoughts.",
        size=BODY_PT,
    )


def problem_slide(d: Deck) -> None:
    d.slide(
        "Introduction: problem and objectives",
        75,
        "The dataset's own paper reports {rqOnePublishedGroupBCspLda:int} to "
        "{rqOnePublishedGroupTCspLda:int}% for telling imagined hand from imagined sixth finger, "
        "but its spatial filters were fitted on all trials before testing, a known source of "
        "optimistic scores. And every BCI must first be calibrated on the user, which for a "
        "patient is effort before any therapy. So we set out to test the dataset without "
        "leakage, measure the calibration a new patient needs with and without other patients' "
        "data, and ask whether the sixth finger can be a command of its own.",
    )
    gap = 20.0
    half = (CW - gap) / 2
    top, height = CT - 2, 306.0
    d.box(CL, top, half, height)
    d.box(CL, top, half, 4, fill="red", line=None, radius=0)
    d.text(
        (CL + 18, top + 16, half - 36, 28),
        "Problem statement",
        size=LEAD_PT,
        bold=True,
        color="navy",
    )
    d.text(
        (CL + 18, top + 52, half - 36, 46),
        "{rqOnePublishedGroupBCspLda:int}–{rqOnePublishedGroupTCspLda:int}%",
        size=STAT_PT,
        bold=True,
        color="red",
    )
    d.text(
        (CL + 18, top + 100, half - 36, 24),
        "Published, hand vs sixth finger",
        size=SMALL_PT,
        color="muted",
    )
    d.bullets(
        (CL + 18, top + 146, half - 36, 150),
        [
            "But its filters also saw the **test trials**",
            "Every user must first **calibrate**: effort for a patient",
        ],
        size=SMALL_PT + 1,
        gap=12,
        mark="red",
    )
    x2 = CL + half + gap
    d.box(x2, top, half, height)
    d.box(x2, top, half, 4, fill="blue", line=None, radius=0)
    d.text((x2 + 18, top + 16, half - 36, 28), "Objectives", size=LEAD_PT, bold=True, color="navy")
    objectives = [
        "Re-test the dataset **leakage-free**",
        "Measure calibration, with and without **other patients**",
        "Test the sixth finger as a **command of its own**",
        "Build a **demonstrator** on held-out data",
    ]
    y = top + 58
    for i, item in enumerate(objectives, start=1):
        paras = d._paras([item], False)
        need = d.height(paras, half - 82, SMALL_PT + 1, 0)
        d.badge(x2 + 30, y + 11, str(i), r=11, fill="blue")
        d.text((x2 + 52, y, half - 70, need + 2), paras, size=SMALL_PT + 1)
        y += max(need, 24) + 14
    d.band(
        (CL, 440, CW, 72),
        [
            [
                *d.rich("Significance  ", bold=True, color="navy"),
                *d.rich(
                    "Shorter set-up for rehabilitation BCIs, and an honest baseline for everyone "
                    "who uses this public dataset."
                ),
            ]
        ],
        size=BODY_PT,
    )


def flowchart_slide(d: Deck) -> None:
    rec = d.slide(
        "Proposed Solution: flowchart",
        60,
        "We took a public recording, audited every file, and cut each trial into windows. Before "
        "any test we froze our hypotheses. Then we ran the leak check and the calibration study, "
        "the exploratory follow-ups after them, and finally built the demonstrator and wrote "
        "everything up with every number taken from the results files.",
        reuse=3,
    )
    d.drop_body()
    rec.settings.append(WINDOW)
    rec.drawn.append(STAGES)
    stages = [
        ("Public data", "{nSubjects} stroke patients", False),
        ("Audit", "{auditPairsScreened} pairs of runs compared", False),
        ("Windows", "<<4 s>> of rest, hand or sixth finger", False),
        ("Plan frozen", "hypotheses fixed before any test", False),
        ("Leak check", "published way vs leakage-free", False),
        ("Calibration", "from scratch vs other patients", False),
        ("Follow-ups", "switch, other days: exploratory", True),
        ("Demonstrator", "held-out replay in the browser", False),
    ]
    gap = 28.0
    bw = (CW - 3 * gap) / 4
    bh = 128.0
    rows = [CT + 8, CT + bh + 60]
    places = []
    for i in range(8):
        row = i // 4
        col = i % 4 if row == 0 else 3 - i % 4
        places.append((CL + col * (bw + gap), rows[row]))
    for i, ((name, what, dashed), (x, y)) in enumerate(zip(stages, places, strict=True)):
        d.box(x, y, bw, bh, line="muted" if dashed else "navy", lw=1.25, dash=dashed)
        # The stage number sits on the card's top edge, leaving the name the full width.
        d.badge(x + 26, y, str(i + 1), r=12, fill="muted" if dashed else "navy")
        d.text((x + 14, y + 22, bw - 26, 26), name, size=SMALL_PT + 1, bold=True, color="navy")
        d.text((x + 14, y + 54, bw - 26, bh - 60), what, size=17)
    for i in range(7):
        (x1, y1), (x2, y2) = places[i], places[i + 1]
        if y1 == y2:
            if x2 > x1:
                d.line(x1 + bw + 4, y1 + bh / 2, x2 - 4, y2 + bh / 2, arrow=True)
            else:
                d.line(x1 - 4, y1 + bh / 2, x2 + bw + 4, y2 + bh / 2, arrow=True)
        else:
            d.line(x1 + bw / 2, y1 + bh + 4, x2 + bw / 2, y2 - 4, arrow=True)
    ly = 474.0
    d.box(CL, ly + 3, 28, 16, line="navy", lw=1.25, radius=3)
    d.text(
        (CL + 38, ly, 330, 24),
        "Solid: pre-registered tests and the system.",
        size=CAPTION_PT,
        color="muted",
    )
    d.box(CL + 360, ly + 3, 28, 16, line="muted", lw=1.25, dash=True, radius=3)
    d.text(
        (CL + 398, ly, CW - 398, 24),
        "Dashed: exploratory, run after the results.",
        size=CAPTION_PT,
        color="muted",
    )


def methodology_slide(d: Deck) -> None:
    d.slide(
        "Proposed Solution: methodology",
        65,
        "Cross-validation splits the trials into learning and test trials. In the published "
        "way, the first step, the spatial filters, studies all trials, the test trials too, "
        "like an exam seen in advance. Leakage-free, it studies only the learning trials. "
        "Every later result learns on runs 1 and 2 and is tested on runs 3 and 4, which no step "
        "ever saw, and the main tests were fixed in the project's git history before they ran, "
        "not with an outside registry.",
        reuse=None,
    )
    d.drop_body()
    _, (cx, cy, cw, _) = d.framed("leak", (CL, CT - 6, 584, 352), pad=6)
    rx = cx + cw + 18
    rw = CR - rx
    items = [
        ("Leakage-free", "every step learns from training trials only"),
        ("Learn", "on runs 1–2"),
        ("Test", "on runs 3–4, never seen"),
        ("Pre-registered", "tests fixed before they ran"),
    ]
    y = cy + 4
    for i, (head, what) in enumerate(items):
        if i:
            d.line(rx, y - 8, CR, y - 8, color="line", lw=0.75)
        paras = [d.rich(head, bold=True, color="blue"), d.rich(what)]
        need = d.height(paras, rw, 17, 2)
        d.text((rx, y, rw, need + 2), paras, size=17, gap=2)
        y += need + 18
    d.band(
        (CL, 476, CW, 40), "The two differ only in what the first step learns from.", size=SMALL_PT
    )


def dataset_slide(d: Deck) -> None:
    rec = d.slide(
        "Dataset",
        70,
        "We recorded no one: all signals come from the public dataset of Wang and colleagues, "
        "{nSubjects} stroke patients from one hospital, on figshare under CC BY 4.0. Each "
        "patient came before two weeks of therapy, after it and a month later, and imagined "
        "either grasping with the affected hand or flexing the sixth finger. Before any analysis "
        "we audited every file and found a copied session, two patients sharing one recording "
        "and a run without imagery; we set them aside, which leaves {nPre} patients before "
        "therapy for the main tests.",
        reuse=4,
    )
    rec.settings.append(DESIGN)
    left = 392.0
    d.bullets(
        (CL, CT + 2, left, 232),
        [
            "**Wang et al., 2026**, on figshare, CC BY 4.0",
            "**{nSubjects} stroke patients**; we recorded no one",
            "<<40>> EEG channels at {nSamplingRate} Hz, preprocessed",
            "Imagine: grasp with the **hand**, or flex the **sixth finger**",
        ],
        size=SMALL_PT + 1,
        gap=12,
    )
    x2 = CL + left + 22
    bw = CR - x2
    top, bh = CT - 2, 228.0
    d.box(x2, top, bw, bh)
    d.box(x2, top, bw, 4, fill="red", line=None, radius=0)
    d.text(
        (x2 + 16, top + 14, bw - 32, 24),
        "Problems we found",
        size=SMALL_PT + 1,
        bold=True,
        color="red",
    )
    d.text(
        (x2 + 16, top + 44, bw - 32, 118),
        [
            "A follow-up session copied from another",
            "sub-21 and sub-22 share one recording",
            "One run with no imagery",
        ],
        size=17,
        gap=6,
    )
    d.line(x2 + 16, top + 168, x2 + bw - 16, top + 168, color="line", lw=0.75)
    d.text(
        (x2 + 16, top + 176, bw - 32, 44),
        "Kept: **{nRunsKept} runs**, **{nPre} patients** before therapy",
        size=17,
        nums="blue",
    )
    # The session design as the page's session.png draws it, in the deck's colours.
    y0 = 364.0
    sessions = ["Before therapy", "After two weeks", "A month later"]
    sgap = 44.0
    sw = (CW - 2 * sgap) / 3
    for i, name in enumerate(sessions):
        x = CL + i * (sw + sgap)
        d.box(x, y0, sw, 60, fill="navy", line=None, radius=8)
        d.text(
            (x + 8, y0 + 7, sw - 16, 46),
            [
                [*d.rich(f"Session <<{i + 1}>>", bold=True, color="white")],
                [*d.rich(name, color="white")],
            ],
            size=17,
            align="c",
            color="white",
        )
        if i:
            d.line(x - sgap + 6, y0 + 30, x - 6, y0 + 30, arrow=True)
    d.text(
        (CL, y0 + 76, CW, 46),
        "Each session: <<4>> runs of <<20>> trials. Rest under a cross, then a picture cue: "
        "imagine for <<6 s>>.",
        size=SMALL_PT,
        align="c",
        color="muted",
    )


def algorithms_slide(d: Deck) -> None:
    rec = d.slide(
        "Experimental Details: algorithms",
        70,
        "CSP with LDA is the dataset paper's method. Our pre-registered pair is TS+LR, a "
        "Riemannian classifier trained on the patient alone, against re-centred transfer, which "
        "first re-centres each patient's data and then learns from the other patients too; its "
        "one chosen setting weighs each of the patient's windows like one of the others' "
        "thousands. EEGNet, a small neural network, runs from scratch or pre-trained on the other "
        "patients and fine-tuned. The move-or-rest switch is an exploratory follow-up.",
        reuse=5,
    )
    rec.settings.append(CENTRAL)
    d.drop_body()
    methods = [
        ("CSP+LDA", "spatial filters, then a straight-line boundary"),
        ("TS+LR", "Riemannian tangent space and logistic regression, patient only"),
        ("Re-centred transfer", "TS+LR with the other patients' data too"),
        ("EEGNet", "compact neural network, from scratch or pre-trained"),
        ("Move-or-rest switch", "TS+LR on <<14>> central channels (exploratory)"),
    ]
    name_w = 196.0
    y = CT - 4
    for i, (name, what) in enumerate(methods):
        paras = d._paras([what], False)
        need = max(d.height(paras, CW - name_w - 8, SMALL_PT + 1, 0), 23)
        if i:
            d.line(CL, y - 7, CR, y - 7, color="line", lw=0.75)
        d.text((CL, y, name_w, need + 2), name, size=SMALL_PT + 1, bold=True, color="navy")
        d.text((CL + name_w, y, CW - name_w, need + 2), paras, size=SMALL_PT + 1)
        y += need + 14
    y += 8
    d.box(CL, y, CW, 516 - y)
    d.text(
        (CL + 16, y + 12, CW - 32, 34),
        [
            [
                *d.rich("EEGNet in the demo   ", bold=True, color="navy"),
                *d.rich("{demoParameters}", bold=True, color="blue", size=26),
                *d.rich(" learned numbers   "),
                *d.rich("{demoModelKb} KB", bold=True, color="blue", size=26),
                *d.rich("   runs in the browser"),
            ]
        ],
        size=SMALL_PT,
    )
    x, py, w, h = d.picture("model", (CL + 16, y + 50, CW - 32, 516 - y - 86), valign="t")
    steps = ["Signal in", "Rhythms", "Sensors", "Combine", "Rest, hand, finger"]
    colw = w / len(steps)
    for i, name in enumerate(steps):
        d.text(
            (x + i * colw, py + h + 4, colw, 22), name, size=CAPTION_PT, align="c", color="muted"
        )


def implementation_slide(d: Deck) -> None:
    rec = d.slide(
        "Experimental Details: implementation",
        55,
        "Everything is software; no hardware was built. The analysis is Python with MNE, "
        "pyRiemann, scikit-learn and braindecode on PyTorch, run on a laptop and, for the long "
        "grids, on Kaggle. The demo's EEGNet is exported to ONNX and runs in the browser inside a "
        "React page, with a FastAPI server on Render streaming the replay. Dashed below: the cap, "
        "amplifier and physical finger a real system still needs.",
    )
    d.drop_body()
    rec.drawn.append(
        "Software as pinned in pyproject.toml, server/pyproject.toml and web/package.json; the "
        "server's host in render.yaml; the long runs' logs under results/kaggle/."
    )
    blocks = [
        ("EEG files", "public recording"),
        ("Python analysis", "MNE, pyRiemann, scikit-learn"),
        ("EEGNet", "braindecode, PyTorch → ONNX"),
        ("Browser demo", "React, ONNX Runtime Web; FastAPI on Render"),
    ]
    gap = 26.0
    bw = (CW - 3 * gap) / 4
    bh = 110.0
    top = CT - 4
    for i, (name, what) in enumerate(blocks):
        x = CL + i * (bw + gap)
        d.box(x, top, bw, bh, line="navy", lw=1.25)
        d.box(x, top, bw, 34, fill="navy", line=None, radius=6)
        d.box(x, top + 26, bw, 8, fill="navy", line=None, radius=0)
        d.text(
            (x + 6, top + 6, bw - 12, 24), name, size=SMALL_PT, bold=True, color="white", align="c"
        )
        d.text((x + 8, top + 42, bw - 16, bh - 46), what, size=CAPTION_PT, align="c")
        if i:
            d.line(x - gap + 4, top + bh / 2 + 10, x - 4, top + bh / 2 + 10, arrow=True)
    d.text(
        (CL, top + bh + 10, CW, 24),
        "Hardware: a laptop ({demoInferenceMachine}) and Kaggle for long runs; no headset or "
        "finger built.",
        size=SMALL_PT,
        color="muted",
        align="c",
    )
    cols = [
        ("path-cap", "Cap and amplifier: needed", False),
        ("path-practice", "Page, server, model: built", True),
        ("path-therapy", "Board, motor, finger: needed", False),
    ]
    cgap = 16.0
    colw = (CW - 2 * cgap) / 3
    ytop = 264.0
    for i, (key, label, built) in enumerate(cols):
        x = CL + i * (colw + cgap)
        d.box(
            x,
            ytop,
            colw,
            516 - ytop,
            line="blue" if built else "muted",
            lw=1.75 if built else 1,
            dash=not built,
        )
        d.picture(key, (x + 14, ytop + 12, colw - 28, 516 - ytop - 70), valign="b")
        d.text(
            (x + 6, 516 - 52, colw - 12, 44),
            label,
            size=SMALL_PT - 1,
            align="c",
            anchor="m",
            bold=built,
            color="blue" if built else "ink",
        )


def leak_result_slide(d: Deck) -> None:
    d.slide(
        "Results: the leak inflates the score",
        80,
        "Rebuilt from their code, the authors' recipe scores {rqOneCspLdaReplicaPaperReplicaMean}% "
        "the published way, above their own figure, and {rqOneCspLdaReplicaCvLeakfreeMean}% "
        "leakage-free; we reproduce the leak, not the published value. Our pre-registered test, "
        "H1, used a standard CSP+LDA: {rqOneCspLdaPaperReplicaMean}% against "
        "{rqOneCspLdaCvLeakfreeMean}%, lower for all {rqOneHOnePositive} patients, a drop of "
        "{rqOneHOneDiff} points, p = {rqOneHOneP}. Leakage-free, hand and sixth finger are only "
        "weakly separable; guessing gets half.",
        reuse=6,
    )
    d.drop_body()
    (x, y, w, h), (cx, cy, cw, ch) = d.framed("leak-slope", (CL, CT - 6, 484, 340), pad=6, below=44)
    k = w / 365
    d.text(
        (x, y + h + 2, 150 * k, 40),
        [[*d.rich("Published way", bold=True, color="red")], "test trials used"],
        size=CAPTION_PT,
        align="c",
    )
    d.text(
        (x + w - 170 * k, y + h + 2, 150 * k, 40),
        [[*d.rich("Leakage-free", bold=True, color="blue")], "kept apart"],
        size=CAPTION_PT,
        align="c",
    )
    rx = cx + cw + 20
    rw = CR - rx
    rows = [
        (
            "{rqOneCspLdaReplicaPaperReplicaMean}%",
            "{rqOneCspLdaReplicaCvLeakfreeMean}%",
            "the authors' recipe, rebuilt",
        ),
        (
            "{rqOneCspLdaPaperReplicaMean}%",
            "{rqOneCspLdaCvLeakfreeMean}%",
            "standard CSP+LDA, pre-registered H1",
        ),
    ]
    yy = cy + 2
    for before, after, what in rows:
        d.text(
            (rx, yy, rw, 36),
            [
                [
                    *d.rich(before, bold=True, color="red"),
                    bs.Span(" → ", bold=True, color="navy"),
                    *d.rich(after, bold=True),
                ]
            ],
            size=28,
            bold=True,
            color="blue",
        )
        d.text((rx, yy + 38, rw, 44), what, size=SMALL_PT - 1, color="muted")
        yy += 98
    d.text(
        (rx, yy, rw, 36), "{rqOneHOnePositive} of {rqOneHOneN}", size=28, bold=True, color="blue"
    )
    d.text(
        (rx, yy + 38, rw, 44),
        ["patients lower,", "p = {rqOneHOneP}"],
        size=SMALL_PT - 1,
        color="muted",
    )
    d.band(
        (CL, cy + ch + 12, CW, 516 - cy - ch - 12),
        "Published: {rqOnePublishedGroupBCspLda:int}–{rqOnePublishedGroupTCspLda:int}%. "
        "Leakage-free, hand and sixth finger are only weakly separable.",
        size=SMALL_PT,
        nums=None,
    )


def comparison_slide(d: Deck) -> None:
    d.slide(
        "Results: comparison with related studies",
        65,
        "The first row is the dataset paper itself, Wang et al. 2026. The same leak raised "
        "scores on two public datasets of healthy people too, by {rqOneBnciHOneBDiff} points on "
        "BNCI 2014-001 and {rqOneChoHOneBDiff} on Cho 2017, pre-registered H1b: the leak comes "
        "from the procedure, not from these recordings. As an exploratory benchmark, healthy "
        "people from the BCI Competition 2020 grasp track (Jeong et al. 2022), trained on one "
        "day and tested a week later, told two grasps of one hand apart only "
        "{exThreeBenchPairsMin} to {exThreeBenchPairsMax}% of the time: two movements of one "
        "hand are hard to separate in anyone.",
    )
    d.drop_body()
    widths = [372.0, 166.0, CW - 372 - 166]
    cols = [CL, CL + widths[0], CL + widths[0] + widths[1]]
    heads = ["Study and data", "With the leak", "Leakage-free"]
    rh = 40.0
    y = CT - 4
    d.box(CL, y, CW, rh, fill="navy", line=None, radius=4)
    for c, wdt, head in zip(cols, widths, heads, strict=True):
        d.text((c + 14, y + 9, wdt - 20, 24), head, size=SMALL_PT, bold=True, color="white")
    rows = [
        (
            "Wang et al., 2026: published",
            "{rqOnePublishedGroupBCspLda}–{rqOnePublishedGroupTCspLda}%",
            "not reported",
        ),
        (
            "Their recipe, rebuilt by us",
            "{rqOneCspLdaReplicaPaperReplicaMean}%",
            "{rqOneCspLdaReplicaCvLeakfreeMean}%",
        ),
        (
            "Standard CSP+LDA, ours ({rqOneHOneN} patients)",
            "{rqOneCspLdaPaperReplicaMean}%",
            "{rqOneCspLdaCvLeakfreeMean}%",
        ),
        (
            "BNCI 2014-001, healthy ({rqOneBnciHOneBN})",
            "{rqOneBnciPaperReplicaMean}%",
            "{rqOneBnciCvLeakfreeMean}%",
        ),
        (
            "Cho 2017, healthy ({rqOneChoHOneBN})",
            "{rqOneChoPaperReplicaMean}%",
            "{rqOneChoCvLeakfreeMean}%",
        ),
    ]
    y += rh
    for i, (label, leaky, clean) in enumerate(rows):
        d.box(CL, y, CW, rh, fill="white" if i % 2 == 0 else "pale", line=None, radius=0)
        d.text((cols[0] + 14, y + 7, widths[0] - 20, 24), label, size=SMALL_PT + 1)
        d.text((cols[1] + 14, y + 7, widths[1] - 20, 24), leaky, size=SMALL_PT + 1, color="red")
        if clean == "not reported":
            d.text(
                (cols[2] + 14, y + 7, widths[2] - 20, 24), clean, size=SMALL_PT + 1, color="muted"
            )
        else:
            d.text(
                (cols[2] + 14, y + 7, widths[2] - 20, 24),
                clean,
                size=SMALL_PT + 1,
                bold=True,
                color="blue",
            )
        y += rh
    d.line(CL, y, CR, y, color="navy", lw=1)
    d.text(
        (CL, y + 8, CW, 24),
        "Hand vs sixth finger for the stroke rows; left vs right hand for the healthy ones.",
        size=CAPTION_PT,
        color="muted",
    )
    by = y + 46
    d.band(
        (CL, by, CW, 72),
        [
            [
                *d.rich("Healthy benchmark, exploratory:", bold=True, color="navy"),
                *d.rich(
                    " BCI Competition 2020 Track 4 (Jeong et al., 2022), {exThreeBenchPeople} "
                    "people, two grasps of one hand a week apart: "
                    "**{exThreeBenchPairsMin}–{exThreeBenchPairsMax}%**"
                ),
            ]
        ],
        size=SMALL_PT,
    )


def calibration_slide(d: Deck) -> None:
    d.slide(
        "Results: calibration for a new patient",
        80,
        "Three choices, rest, hand or sixth finger, where guessing gets a third. With one trial "
        "of each movement, about {rqTwoMinutesKOne:sec} seconds, re-centred transfer reaches "
        "{rqTwoRestAhSfRctTslrKOneMean}% against {rqTwoRestAhSfTsLrKOneMean}% from scratch; "
        "pre-registered H2a held, p = {rqTwoHTwoAP}. That is one transfer configuration, and "
        "part of the lead is how little a decoder learns from four windows. Then transfer stays "
        "flat; with all the practice, {rqTwoMinutesKAll} minutes nominal, from scratch ends "
        "{rqTwoRestAhSfTsLrMinusRctTslrKAllDiff} points higher, a difference we did not test. On "
        "another day, exploratory, an unchanged decoder falls to {rqFourLaterPostUnchangedMean}% "
        "and five new trials of each movement bring it back to "
        "{rqFourLaterPostRecentredKFiveMean}%.",
    )
    d.drop_body()
    _, (cx, cy, cw, ch) = d.framed("setup", (CL, CT - 6, 584, 330), pad=6)
    rx = cx + cw + 16
    rw = CR - rx
    d.text(
        (rx, cy + 2, rw, 44),
        "{rqTwoRestAhSfRctTslrKOneMean}%",
        size=STAT_PT,
        bold=True,
        color="blue",
    )
    d.text((rx, cy + 48, rw, 66), "with other patients, after {rqTwoMinutesKOne:sec} s", size=17)
    d.text(
        (rx, cy + 128, rw, 44),
        "{rqTwoRestAhSfTsLrKOneMean}%",
        size=STAT_PT,
        bold=True,
        color="muted",
    )
    d.text((rx, cy + 174, rw, 66), "from scratch, same practice", size=17)
    d.line(rx, cy + 254, CR, cy + 254, color="line", lw=0.75)
    d.text((rx, cy + 264, rw, 44), "Guessing: one in three", size=17, color="muted")
    ny = cy + ch + 10
    half = (CW - 20) / 2
    d.text(
        (CL, ny, half, 516 - ny),
        "**One transfer configuration** (H2a, p = {rqTwoHTwoAP}). With all "
        "{rqTwoMinutesKAll} min, from scratch ends {rqTwoRestAhSfTsLrMinusRctTslrKAllDiff} "
        "points higher: **not tested**.",
        size=CAPTION_PT,
    )
    d.text(
        (CL + half + 20, ny, half, 516 - ny),
        "**Another day (exploratory)**: unchanged {rqFourLaterPostUnchangedMean}%; five new "
        "trials of each movement, {rqFourLaterPostRecentredKFiveMean}%.",
        size=CAPTION_PT,
        nums="blue",
    )


def switch_slide(d: Deck) -> None:
    rec = d.slide(
        "Results: a new command, or a switch?",
        80,
        "Our pre-registered tests found no distinct sixth-finger command: transfer showed no "
        "clear benefit for it, and a decoder that never saw a sixth-finger trial detected one "
        "as well. Told apart from rest, in an exploratory follow-up, the sixth finger is "
        "recognised {exFourTsLrCentralMean}% of the time per window, but the same switch fires on "
        "{exFourTsLrCentralFiresAhMean}% of hand-imagery windows, so it detects imagined movement, "
        "not the finger. Played continuously it caught {exFiveFingerFingerOnMean}% of "
        "sixth-finger periods with {exFiveFingerFalsePerMinMean} false switch-ons a minute, and "
        "no decoder drove a finger. Rest was always a cross and imagery a picture: finger against "
        "rest decodes better from central channels, {rqFourCueSfRestCentralMean} against "
        "{rqFourCueSfRestParietoOccipitalMean}%, but hand against finger better from the visual "
        "ones, {rqFourCueAhSfParietoOccipitalMean} against {rqFourCueAhSfCentralMean}%, so that "
        "weak signal may come partly from the pictures.",
    )
    d.drop_body()
    rec.settings += [CENTRAL, REPLAY]
    _, (cx, cy, cw, ch) = d.framed("switch-patients", (CL, CT - 6, 570, 326), pad=6)
    rx = cx + cw + 16
    rw = CR - rx
    d.box(rx, cy + 2, 112, 26, fill="cream", line="gold", lw=1, radius=13)
    d.text(
        (rx, cy + 5, 112, 20), "Exploratory", size=CAPTION_PT, bold=True, color="navy", align="c"
    )
    d.text(
        (rx, cy + 40, rw, 40), "{exFourTsLrCentralFiresAhMean}%", size=30, bold=True, color="red"
    )
    d.text((rx, cy + 80, rw, 60), "of hand windows fire it too", size=17)
    d.text((rx, cy + 146, rw, 40), "{exFiveFingerFingerOnMean}%", size=30, bold=True, color="blue")
    d.text(
        (rx, cy + 186, rw, 84),
        "of periods caught, continuous; {exFiveFingerFalsePerMinMean} false a minute",
        size=17,
    )
    d.line(rx, cy + 278, CR, cy + 278, color="line", lw=0.75)
    d.text((rx, cy + 288, rw, 24), "No finger driven", size=17, color="muted")
    ny = cy + ch + 10
    half = (CW - 20) / 2
    d.band(
        (CL, ny, half, 516 - ny),
        "**No distinct sixth-finger command** (H3, H3c inconclusive): a move-or-rest switch.",
        size=CAPTION_PT,
    )
    d.text(
        (CL + half + 20, ny + 4, half, 516 - ny - 4),
        "Visual cues: finger vs rest best centrally ({rqFourCueSfRestCentralMean} vs "
        "{rqFourCueSfRestParietoOccipitalMean}%); hand vs finger best occipitally "
        "({rqFourCueAhSfParietoOccipitalMean} vs {rqFourCueAhSfCentralMean}%).",
        size=CAPTION_PT,
    )


def conclusion_slide(d: Deck) -> None:
    d.slide(
        "Conclusion",
        45,
        "In one sentence: tested without leakage, hand and sixth finger are barely separable; "
        "one transfer configuration gives a new patient a fast start and then stays flat; and the "
        "sixth finger is so far a move-or-rest switch, not a command of its own. Next, we would "
        "test that switch in closed loop driving a real finger, and try transfer that keeps "
        "learning as the patient practises.",
        reuse=7,
    )
    d.drop_body()
    top, bh = CT - 2, 176.0
    d.box(CL, top, CW, bh)
    d.box(CL, top, 6, bh, fill="blue", line=None, radius=0)
    d.text(
        (CL + 26, top + 14, CW - 46, bh - 28),
        "Leakage-free, hand against sixth finger scores {rqOneCspLdaReplicaCvLeakfreeMean}–"
        "{rqOneCspLdaCvLeakfreeMean}%, not the published {rqOnePublishedGroupBCspLda:int}%; "
        "one transfer configuration lifts a new patient from {rqTwoRestAhSfTsLrKOneMean}% to "
        "{rqTwoRestAhSfRctTslrKOneMean}% after one trial of each movement, then stays flat; and "
        "the sixth finger is, so far, a **move-or-rest switch**, not a command of its own.",
        size=LEAD_PT,
        anchor="m",
        nums="blue",
    )
    fy = top + bh + 28
    d.text((CL, fy, CW, 30), "Future work", size=LEAD_PT, bold=True, color="navy")
    future = [
        ("Closed loop", "the switch drives a real finger, with patients"),
        ("Transfer that keeps learning", "e.g. a weight that grows with practice"),
    ]
    gap = 20.0
    fw = (CW - gap) / 2
    cy = fy + 40
    for i, (head, what) in enumerate(future):
        x = CL + i * (fw + gap)
        d.box(x, cy, fw, 96)
        d.badge(x + 30, cy + 30, str(i + 1), r=13, fill="blue")
        d.text(
            (x + 56, cy + 14, fw - 72, 76),
            [d.rich(head, bold=True, color="navy"), d.rich(what)],
            size=BODY_PT - 1,
            gap=4,
        )


def demo_slide(d: Deck) -> None:
    rec = d.slide(
        "Live demo",
        DEMO_SECONDS,
        "This is patient {demoSubject}, a recording the model never learned from: it learned "
        "from this patient's runs 1 and 2 only, {demoTrainingTrials} trials, and what plays now "
        "is the last two runs, {demoTrials} whole trials, at real speed. Left is the cue the "
        "patient saw, the middle is the EEG, right is the model's reading with a tick or a "
        "cross; on this patient it is right {demoHeldOutAcc}% of the time on three choices. "
        f"If the page does not load, open {SITE_COPY}/live, or play the recorded video "
        "(~/Movies/sixth-finger-bci-demo-backup.mp4, also on the USB stick).",
        part="demo",
    )
    rec.settings += [WINDOW, REPLAY]
    lw = 470.0
    d.box(CL, CT + 2, lw, 54, fill="navy", line=None, radius=8)
    d.text((CL + 18, CT + 14, lw - 36, 32), SITE + "/live", size=26, bold=True, color="white")
    d.bullets(
        (CL, CT + 86, lw, 230),
        [
            "Patient **{demoSubject}**, runs the model never saw",
            "Left: the cue. Middle: the EEG. Right: the model's reading",
            "Real held-out predictions, at real speed",
        ],
        size=BODY_PT,
        gap=16,
    )
    d.framed("hand-finger", (CR - 210, CT + 2, 210, 394), pad=14, align="r", valign="t")
    d.line(CL, 452, CR, 452, color="line", lw=0.75)
    d.text(
        (CL, 462, CW, 44),
        f"If it does not load: {SITE_COPY}/live, or the recorded video",
        size=SMALL_PT - 1,
        color="muted",
        anchor="b",
    )


def questions_slide(d: Deck) -> None:
    d.keep(
        8,
        0,
        "Thank you; we are happy to take questions. Likely ones: why the published score "
        "differs (the leak, slide on results), why so few minutes of practice (transfer), and "
        "what the finger is today (a candidate move-or-rest switch, tested offline only).",
        part="questions",
    )


def thanks_slide(d: Deck) -> None:
    rec = d.keep(
        9,
        10,
        f"Thank you. The page with the live demo and every result in this talk is at {SITE}.",
    )
    t = rec.slide.shapes.title
    tx = t.left / 12700 + 7.2
    d.box(tx, 326, 64, 3.5, fill="gold", line=None, radius=0)
    d.text((tx, 342, CR - tx, 34), SITE, size=26, bold=True, color="blue")
    d.text(
        (tx, 384, CR - tx, 26), "   ·   ".join(n for n, _ in STUDENTS), size=SMALL_PT, color="ink"
    )
    rec.drawn.append(f"The same page is also at {SITE_COPY}.")


TALK = [
    title_slide,
    contents_slide,
    background_slide,
    bci_slide,
    problem_slide,
    flowchart_slide,
    methodology_slide,
    dataset_slide,
    algorithms_slide,
    implementation_slide,
    leak_result_slide,
    comparison_slide,
    calibration_slide,
    switch_slide,
    conclusion_slide,
    demo_slide,
    questions_slide,
    thanks_slide,
]


# Output


def finish(prs: Presentation) -> bytes:
    """Save with the students as authors and fixed dates, so an unchanged deck is the same file."""
    cp = prs.core_properties
    cp.author = ", ".join(name for name, _ in STUDENTS)
    cp.last_modified_by = STUDENTS[0][0]
    cp.title = TOPIC
    cp.subject = "Minor project presentation, Department of ECE, MSIT"
    cp.keywords = "EEG, motor imagery, stroke, brain-computer interface, sixth finger"
    cp.comments = ""
    cp.category = ""
    cp.revision = 1
    cp.created = cp.modified = datetime(*STAMP)
    cp.last_printed = datetime(*STAMP)
    raw = io.BytesIO()
    prs.save(raw)
    out = io.BytesIO()
    n_slides = len(prs.slides)
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
        'docPropsVTypes"><Template>Wisp</Template><TotalTime>0</TotalTime>'
        "<Application>Microsoft Office PowerPoint</Application>"
        f"<PresentationFormat>Widescreen</PresentationFormat><Slides>{n_slides}</Slides>"
        f"<Notes>{n_slides}</Notes><HiddenSlides>0</HiddenSlides><Company></Company>"
        "<AppVersion>16.0000</AppVersion></Properties>"
    ).encode()
    with zipfile.ZipFile(raw) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = app if item.filename == "docProps/app.xml" else zin.read(item.filename)
            zout.writestr(info, data)
    return out.getvalue()


def reorder(d: Deck) -> None:
    """Put the slides in the order the talk built them, template slides included."""
    lst = d.prs.slides._sldIdLst
    ids = list(lst)
    by_part = {d.prs.part.related_part(e.rId): e for e in ids}
    for e in ids:
        lst.remove(e)
    for rec in d.records:
        lst.append(by_part[rec.slide.part])
    if len(lst) != len(ids):
        raise ValueError("a template slide was left out of the talk")


def export_pdf(pptx: Path) -> Path:
    """A PDF beside the deck through LibreOffice, with the deck's fonts in a private profile."""
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        fonts = profile / "user" / "fonts"
        fonts.mkdir(parents=True)
        for family in ("Arial", "Georgia", "Wingdings 3"):
            for ttf in SUPPLEMENTAL.glob(f"{family}*.ttf"):
                shutil.copy(ttf, fonts)
        subprocess.run(
            [
                str(SOFFICE),
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pptx.parent),
                str(pptx),
            ],
            check=True,
            timeout=600,
            capture_output=True,
        )
    return pptx.with_suffix(".pdf")


def check_pdf_fonts(pdf: Path) -> list[str]:
    """Every font in the PDF must be embedded and be one the deck names."""
    out = subprocess.run(["pdffonts", str(pdf)], check=True, capture_output=True, text=True)
    problems = []
    for line in out.stdout.splitlines()[2:]:
        name = line.split()[0].split("+")[-1]
        flags = re.search(r"\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", line)
        embedded = flags.group(1) if flags else "no"
        if not name.startswith(PDF_FONTS):
            problems.append(f"PDF font {name} is not one of the deck's")
        if embedded != "yes":
            problems.append(f"PDF font {name} is not embedded")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", type=Path, default=TEMPLATE, help="the college's template")
    parser.add_argument("--pdf", action="store_true", help="also export a PDF with LibreOffice")
    parser.add_argument("--previews", action="store_true", help="draw the PDF's pages as PNGs")
    args = parser.parse_args()

    d = Deck(args.template, bs.load_macros(), json.loads(bs.PAGE_DATA.read_text()))
    for make in TALK:
        make(d)
    reorder(d)
    d.retype()
    for rec in d.records[1:]:
        d.number_slide(rec)
    d.notes()

    problems = d.check_text() + d.check_shapes() + d.check_figures()
    talk = sum(r.seconds for r in d.records if r.part == "talk")
    if talk != TALK_SECONDS:
        problems.append(f"the talk comes to {talk} s, not {TALK_SECONDS}")
    blob = finish(d.prs)
    if len(blob) > MAX_BYTES:
        problems.append(f"the deck is {len(blob) / 1e6:.1f} MB, over 5 MB")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    OUT.write_bytes(blob)
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(d.records)} slides, {len(blob) / 1e6:.2f} MB, "
        f"talk {talk // 60}:{talk % 60:02d} + demo {DEMO_SECONDS // 60}:00"
    )
    for rec in d.records:
        when = "demo" if rec.part == "demo" else f"{rec.seconds // 60}:{rec.seconds % 60:02d}"
        figs = ", ".join(FIGS[k].file for k in rec.figures) or "-"
        print(f"  {rec.no:2d}  {when:>5}  {rec.title}  [{figs}]")
    if args.pdf or args.previews:
        pdf = export_pdf(OUT)
        bad = check_pdf_fonts(pdf)
        if bad:
            print("\n".join(bad), file=sys.stderr)
            return 1
        print(f"wrote {pdf.relative_to(ROOT)}, fonts embedded: Georgia, Arial, Wingdings 3")
        if args.previews:
            if PREVIEWS.exists():
                shutil.rmtree(PREVIEWS)
            PREVIEWS.mkdir()
            subprocess.run(
                ["pdftoppm", "-r", "96", "-png", str(pdf), str(PREVIEWS / "slide")], check=True
            )
            drawn = len(list(PREVIEWS.glob("*.png")))
            print(f"drew {drawn} pages into {PREVIEWS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
