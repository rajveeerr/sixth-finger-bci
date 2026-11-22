"""Build the final presentation in the college's template, Sixth-Finger-BCI-Final-PPT.pptx.

uv run --with python-pptx==1.0.2 python report/slides/college/build_college_ppt.py
uv run --with python-pptx==1.0.2 python report/slides/college/build_college_ppt.py --pdf --previews

The deck starts from a copy of the college's "Final PPT.pptx", so its master, layouts, logo,
background, Times New Roman and blue titles are the template's own, and keeps its order: title,
contents, introduction, proposed solution, dataset, experimental details, results, conclusion,
questions, thank you. Numbers come from paper/generated/numbers.tex through the macros of
../build_slides.py, written in the slide text as {macroName}; the speaker notes give each one with
its results file. The build fails on text under 16 pt, text that does not fit its box, a figure
whose smallest text would print under 16 pt, a digit typed by hand, or a talk that is not 15:00.

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
from pptx.enum.dml import MSO_LINE_DASH_STYLE, MSO_THEME_COLOR
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
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

# The template's slide in points and the frame its "Title and Content" layout leaves free of the
# curves on the left.
W, H = 960.0, 540.0
LEFT, RIGHT = 200.0, 922.0
BODY_W = RIGHT - LEFT
TOP, BOTTOM = 116.0, 526.0
TITLE_BOX = (204.2, 40.0, 701.7, 62.0)
TITLE_PT = 36.0
MIN_PT = 16.0
TALK_SECONDS = 15 * 60
DEMO_SECONDS = 3 * 60
MAX_BYTES = 5_000_000
FONT = "Times New Roman"
STUDENTS = [
    ("Rajveer Singh", "05096302823"),
    ("Vivek Yadav", "05196302823"),
    ("Ansh Dahiya", "35396302823"),
]
GUIDE = ["Dr. Suman Lata", "Assistant Professor", "Department of ECE, MSIT"]
TOPIC = "EEG-Based Adaptive Brain–Computer Interface for Novel Artificial Limb Control"
SITE = "sixthfinger.rajveers.com"
SITE_COPY = "sixth-finger-bci.vercel.app"
STAMP = (2026, 11, 22, 0, 0, 0)

# Digits a slide may carry without a macro: years, run, session and hypothesis names, patient
# codes, the licence, named datasets.
FREE_DIGITS = re.compile(
    r"\b(?:19|20)\d\d\b|\bruns? \d(?:[–-]\d)?\b|\bsub-\d+\b|\bH\d[abc]?\b|CC BY 4\.0"
    r"|BNCI 2014-001|Track 4|\bk = \d\b",
)
# Words the revised paper dropped, so the deck may not bring them back.
BANNED = re.compile(r"\bfair(?:ly)?\b|overtak|works best", re.IGNORECASE)

# Theme colours of the template: (theme colour, brightness), as the master writes them.
THEME = {
    "title": (MSO_THEME_COLOR.ACCENT_2, -0.25),
    "body": (MSO_THEME_COLOR.TEXT_1, 0.25),
    "dark": (MSO_THEME_COLOR.TEXT_2, 0.0),
    "muted": (MSO_THEME_COLOR.TEXT_1, 0.45),
    "white": (MSO_THEME_COLOR.BACKGROUND_1, 0.0),
    "pale": (MSO_THEME_COLOR.BACKGROUND_2, 0.0),
}


# Text measurement with the template's own font


class Measure:
    """Widths and line height of Times New Roman, read from the font files."""

    def __init__(self) -> None:
        names = {
            (False, False): "Times New Roman.ttf",
            (True, False): "Times New Roman Bold.ttf",
            (False, True): "Times New Roman Italic.ttf",
            (True, True): "Times New Roman Bold Italic.ttf",
        }
        self.fonts = {k: ImageFont.truetype(str(SUPPLEMENTAL / v), 1000) for k, v in names.items()}
        ascent, descent = self.fonts[(False, False)].getmetrics()
        # PowerPoint and LibreOffice both set single spacing a little above ascent + descent.
        self.line = (ascent + descent) / 1000 * 1.04

    def width(self, text: str, size: float, bold: bool, italic: bool = False) -> float:
        return self.fonts[(bold, italic)].getlength(text) * size / 1000

    def lines(self, spans: list[bs.Span], width: float, size: float) -> int:
        words: list[tuple[str, float, bool, bool]] = []
        for sp in spans:
            sz = (sp.size or size) * (0.6 if sp.sup else 1)
            for word in re.split(r"(\s+)", sp.text):
                if word:
                    words.append((word, sz, bool(sp.bold), sp.italic))
        lines, used = 1, 0.0
        for word, sz, b, i in words:
            w = self.width(word, sz, b, i)
            if word.isspace():
                used += w
                continue
            if used and used + w > width + 0.5:
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
    """The figure cropped, with its white taken out so the template's background shows."""
    im = Image.open(bs.FIGURES / fig.file)
    if im.mode == "RGBA":
        white = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(white, im)
    im = im.convert("RGB")
    if fig.crop:
        im = im.crop(fig.crop)
    rgb = np.clip(np.asarray(im).astype(np.float64) / fig.paper, 0, 1)
    # Undo "drawn over white": the least alpha that explains each pixel, and its colour.
    alpha = 1 - rgb.min(axis=2)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    colour = np.clip((rgb - (1 - alpha[..., None])) / safe, 0, 1)
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

    @staticmethod
    def _colour(font: Any, name: str) -> None:
        theme, brightness = THEME[name]
        font.color.theme_color = theme
        if brightness:
            font.color.brightness = brightness

    def _runs(self, p: Any, spans: list[bs.Span], size: float, color: str) -> None:
        for sp in spans:
            r = p.add_run()
            r.text = sp.text
            f = r.font
            f.name = FONT
            f.size = Pt(sp.size or size)
            f.bold = bool(sp.bold)
            f.italic = sp.italic
            self._colour(f, sp.color or color)
            if sp.sup:
                f._rPr.set("baseline", "30000")

    def _paras(self, paras: list[str | list[bs.Span]], bold: bool, **style: Any) -> list:
        return [p if isinstance(p, list) else self.rich(p, bold=bold, **style) for p in paras]

    def text(
        self,
        box: tuple[float, float, float, float],
        paras: str | list[str | list[bs.Span]],
        size: float = 20,
        bold: bool = False,
        color: str = "body",
        align: str = "l",
        anchor: str = "t",
        gap: float = 0,
        italic: bool = False,
    ) -> Any:
        x, y, w, h = box
        if isinstance(paras, str):
            paras = [paras]
        resolved = self._paras(paras, bold, italic=italic)
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
            self._runs(p, spans, size, color)
        self.boxes.append(TextBox(self.rec.no, resolved, size, w, h, gap))
        return shape

    def bullets(
        self,
        box: tuple[float, float, float, float],
        items: list[str],
        size: float = 20,
        gap: float = 10,
        color: str = "body",
    ) -> Any:
        """Bullets in the template's own body placeholder, with its arrow bullets."""
        x, y, w, h = box
        ph = self._body()
        ph.left, ph.top, ph.width, ph.height = Pt(x), Pt(y), Pt(w), Pt(h)
        tf = ph.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.text = ""
        resolved = self._paras(items, False)
        for i, spans in enumerate(resolved):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(gap if i else 0)
            p.line_spacing = 1.0
            self._runs(p, spans, size, color)
        # Placeholder insets (7.2 pt a side, 3.6 top and bottom) and the bullet's 27 pt indent.
        self.boxes.append(TextBox(self.rec.no, resolved, size, w - 14.4 - 27, h - 7.2, gap))
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
            spans = self.rich(title, bold=True)
            p = tf.paragraphs[0]
            for sp in spans:
                r = p.add_run()
                r.text = sp.text
                r.font.name = FONT
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
        line: str | None = "dark",
        lw: float = 1.25,
        dash: bool = False,
        radius: float = 8,
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
            theme, brightness = THEME[fill]
            shape.fill.fore_color.theme_color = theme
            if brightness:
                shape.fill.fore_color.brightness = brightness
        else:
            shape.fill.background()
        if line:
            theme, brightness = THEME[line]
            shape.line.color.theme_color = theme
            if brightness:
                shape.line.color.brightness = brightness
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
        color: str = "dark",
        lw: float = 1.5,
        arrow: bool = False,
        dash: bool = False,
    ) -> Any:
        c = self.rec.slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Pt(x1), Pt(y1), Pt(x2), Pt(y2)
        )
        self._plain(c)
        theme, brightness = THEME[color]
        c.line.color.theme_color = theme
        if brightness:
            c.line.color.brightness = brightness
        c.line.width = Pt(lw)
        if dash:
            c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if arrow:
            ln = c.line._get_or_add_ln()
            etree.SubElement(ln, qn("a:tailEnd"), type="triangle", w="med", len="med")
        return c

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

    # Checks

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
                height += self.measure.lines(p, b.w, b.size) * size * self.measure.line
                if i:
                    height += b.gap
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
    by_hand = shapes[1]
    topic = shapes[2]
    guide = shapes[3]

    def refill(shape: Any, paras: list[list[bs.Span]], size: float, box_w: float) -> None:
        tf = shape.text_frame
        tf.auto_size = MSO_AUTO_SIZE.NONE
        body = tf._txBody.find(qn("a:bodyPr"))
        for fit in body.findall(qn("a:normAutofit")):
            body.remove(fit)
        tf.text = ""
        for i, spans in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            for sp in spans:
                r = p.add_run()
                r.text = sp.text
                r.font.name = FONT
                r.font.bold = True
                r.font.size = Pt(size)
        h = shape.height / 12700
        d.boxes.append(TextBox(rec.no, paras, size, box_w - 14.4, h - 7.2, size * 0.3))

    names = [[bs.Span("By:", bold=True)]] + [
        [bs.Span(f"{name} ({number})", bold=True, free=True)] for name, number in STUDENTS
    ]
    refill(by_hand, names, 18, by_hand.width / 12700)
    for p in by_hand.text_frame.paragraphs:
        p.alignment = PP_ALIGN.LEFT
        p.space_before = Pt(4)

    refill(topic, [[bs.Span(TOPIC, bold=True)]], 26, topic.width / 12700)
    topic.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    topic.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

    guide.width = Pt(W - 20 - guide.left / 12700)
    paras = [[bs.Span("Under the guidance of:", bold=True)]]
    paras += [[bs.Span(line, bold=True)] for line in GUIDE]
    refill(guide, paras, 18, guide.width / 12700)
    for p in guide.text_frame.paragraphs:
        p.alignment = PP_ALIGN.LEFT
    rec.drawn.append(
        "The enrolment numbers on this slide are why this deck never goes on the website."
    )


def contents_slide(d: Deck) -> None:
    d.keep(
        1,
        10,
        "The talk follows the college's order: why the problem matters, what we did, the data, "
        "how we did it, what we found, and what it means; the live demo comes just before "
        "questions.",
    )


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
        (LEFT - 6, TOP + 10, 368, 320),
        [
            "**Stroke** often leaves one hand too weak to grip",
            "A **robotic sixth finger**, worn on that wrist, grips against the palm",
            "Aim: the patient **imagines** moving it, and it moves",
        ],
        size=22,
        gap=16,
    )
    pw, ph = 172.0, 192.0
    x0 = RIGHT - 2 * pw - 8
    _, y, _, h = d.picture("hand-rest", (x0, TOP + 14, pw, ph))
    d.picture("hand-finger", (x0 + pw + 8, TOP + 14, pw, ph))
    d.text((x0, y + h + 8, pw, 22), "at rest", size=18, align="c", color="muted")
    d.text((x0 + pw + 8, y + h + 8, pw, 22), "bent to grip", size=18, align="c", color="muted")
    d.text(
        (LEFT, 470, BODY_W, 44),
        [
            "BCI therapy after stroke: Cervera et al., 2018. Extra robotic fingers: "
            "Prattichizzo et al., 2021; Kieliba et al., 2021."
        ],
        size=16,
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
    x, y, w, _ = d.picture("system", (LEFT, TOP, BODY_W, 290))
    crop = FIGS["system"].crop or (0, 0, 0, 0)
    k = w / (crop[2] - crop[0])
    # The drawing's own numbers print small; larger ones are laid over them.
    centres = [(461, 382), (741, 434), (1039, 489), (1609.5, 593), (1820.5, 631)]
    for i, (cx, cy) in enumerate(centres, start=1):
        px, py = x + (cx - crop[0]) * k, y + (cy - crop[1]) * k
        d.box(px - 14, py - 14, 28, 28, fill="white", line="dark", lw=1.25, oval=True)
        d.text(
            (px - 14, py - 13, 28, 26),
            [[bs.Span(str(i), bold=True, free=True)]],
            size=18,
            align="c",
            anchor="m",
            color="dark",
        )
    names = ["EEG cap", "Amplifier", "<<4 s>> of signal", "Model", "Robotic finger"]
    cw = BODY_W / len(names)
    for i, name in enumerate(names, start=1):
        spans = [bs.Span(f"{i} ", bold=True, free=True, color="dark"), *d.rich(name)]
        d.text((LEFT + (i - 1) * cw, 416, cw, 24), [spans], size=18, align="c")
    d.text(
        (LEFT, 458, BODY_W, 56),
        "It spots a trained pattern: imagining a movement weakens the **mu rhythm** over the "
        "motor area. It does not read thoughts.",
        size=20,
        align="c",
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
    half = (BODY_W - 30) / 2
    d.text((LEFT, TOP, half, 30), "Problem statement", size=22, bold=True, color="dark")
    d.bullets(
        (LEFT - 6, TOP + 34, half + 6, 250),
        [
            "Published: **{rqOnePublishedGroupBCspLda:int}–{rqOnePublishedGroupTCspLda:int}%**, "
            "hand vs sixth finger",
            "But its filters also saw the **test trials**",
            "Every user must first **calibrate**: effort for a patient",
        ],
        size=20,
        gap=12,
    )
    x2 = LEFT + half + 30
    d.text((x2, TOP, half, 30), "Objectives", size=22, bold=True, color="dark")
    d.bullets(
        (x2 - 6, TOP + 34, half + 6, 250),
        [
            "Re-test the dataset **leakage-free**",
            "Measure calibration, with and without **other patients**",
            "Test the sixth finger as a **command of its own**",
            "Build a **demonstrator** on held-out data",
        ],
        size=20,
        gap=12,
    )
    d.line(LEFT, 398, RIGHT, 398, color="muted", lw=0.75)
    d.text(
        (LEFT, 410, BODY_W, 100),
        [
            [*d.rich("Significance", bold=True, color="dark")],
            "Shorter set-up for rehabilitation BCIs, and an honest baseline for everyone who "
            "uses this public dataset.",
        ],
        size=20,
        gap=4,
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
    gap = 24.0
    bw = (BODY_W - 3 * gap) / 4
    bh = 112.0
    rows = [TOP + 14, TOP + 14 + bh + 56]
    places = []
    for i in range(8):
        row = i // 4
        col = i % 4 if row == 0 else 3 - i % 4
        places.append((LEFT + col * (bw + gap), rows[row]))
    for i, ((name, what, dashed), (x, y)) in enumerate(zip(stages, places, strict=True)):
        d.box(x, y, bw, bh, fill="white", line="dark", lw=1.5, dash=dashed)
        number = bs.Span(f"{i + 1}  ", bold=True, free=True, color="title")
        head = [number, *d.rich(name, bold=True, color="dark")]
        d.text((x + 8, y + 10, bw - 16, 26), [head], size=19)
        d.text((x + 8, y + 40, bw - 16, bh - 48), what, size=18)
    for i in range(7):
        (x1, y1), (x2, y2) = places[i], places[i + 1]
        if y1 == y2:
            if x2 > x1:
                d.line(x1 + bw + 3, y1 + bh / 2, x2 - 3, y2 + bh / 2, arrow=True)
            else:
                d.line(x1 - 3, y1 + bh / 2, x2 + bw + 3, y2 + bh / 2, arrow=True)
        else:
            d.line(x1 + bw / 2, y1 + bh + 3, x2 + bw / 2, y2 - 3, arrow=True)
    d.text(
        (LEFT, 476, BODY_W, 44),
        "Solid: pre-registered tests and the system. Dashed: exploratory, run after the results.",
        size=18,
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
    x, _, w, _ = d.picture("leak", (LEFT, TOP, 560, 342), align="l", valign="t")
    rx = x + w + 22
    d.text(
        (rx, TOP + 10, RIGHT - rx, 330),
        [
            [*d.rich("Leakage-free", bold=True, color="dark")],
            "every step learns from training trials only",
            [*d.rich("Learn", bold=True, color="dark")],
            "on runs 1–2",
            [*d.rich("Test", bold=True, color="dark")],
            "on runs 3–4, never seen",
            [*d.rich("Pre-registered", bold=True, color="dark")],
            "tests fixed before they ran",
        ],
        size=18,
        gap=4,
    )
    d.text(
        (LEFT, 470, BODY_W, 48),
        "The two differ only in what the first step learns from.",
        size=18,
        color="muted",
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
    half = 396.0
    d.bullets(
        (LEFT - 6, TOP, half + 6, 238),
        [
            "**Wang et al., 2026**, on figshare, CC BY 4.0",
            "**{nSubjects} stroke patients**; we recorded no one",
            "<<40>> EEG channels at {nSamplingRate} Hz, preprocessed",
            "Imagine: grasp with the **hand**, or flex the **sixth finger**",
        ],
        size=20,
        gap=10,
    )
    x2 = LEFT + half + 24
    bw = RIGHT - x2
    d.box(x2, TOP + 2, bw, 226, fill="white", line="muted", lw=1, radius=10)
    d.text(
        (x2 + 14, TOP + 12, bw - 28, 210),
        [
            [*d.rich("Problems we found", bold=True, color="dark")],
            "A follow-up session copied from another",
            "sub-21 and sub-22 share one recording",
            "One run with no imagery",
            [*d.rich("Kept: **{nRunsKept} runs**, **{nPre} patients** before therapy")],
        ],
        size=18,
        gap=8,
    )
    # The session design as the page's session.png draws it, in the template's colours.
    y0 = 372.0
    sessions = ["Before therapy", "After two weeks", "A month later"]
    sw = (BODY_W - 2 * 40) / 3
    for i, name in enumerate(sessions):
        x = LEFT + i * (sw + 40)
        d.box(x, y0, sw, 58, fill="pale", line=None, radius=8)
        d.text(
            (x + 8, y0 + 6, sw - 16, 46),
            [[*d.rich(f"Session <<{i + 1}>>", bold=True, color="dark")], name],
            size=18,
            align="c",
        )
        if i:
            d.line(x - 36, y0 + 29, x - 4, y0 + 29, arrow=True)
    d.text(
        (LEFT, y0 + 72, BODY_W, 60),
        "Each session: <<4>> runs of <<20>> trials. Rest under a cross, then a picture cue: "
        "imagine for <<6 s>>.",
        size=18,
        align="c",
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
    d.bullets(
        (LEFT - 6, TOP - 4, BODY_W + 6, 262),
        [
            "**CSP+LDA**: spatial filters, then a straight-line boundary",
            "**TS+LR**: Riemannian tangent space and logistic regression, patient only",
            "**Re-centred transfer**: TS+LR with the other patients' data too",
            "**EEGNet**: compact neural network, from scratch or pre-trained",
            "**Move-or-rest switch**: TS+LR on <<14>> central channels (exploratory)",
        ],
        size=20,
        gap=8,
    )
    d.text(
        (LEFT, 330, BODY_W, 26),
        "**EEGNet in the demo**: {demoParameters} learned numbers, {demoModelKb} KB, runs in "
        "the browser",
        size=18,
        color="dark",
    )
    x, y, w, h = d.picture("model", (LEFT, 366, BODY_W, 96), valign="t")
    steps = ["Signal in", "Rhythms", "Sensors", "Combine", "Rest, hand, finger"]
    cw = w / len(steps)
    for i, name in enumerate(steps):
        d.text((x + i * cw, y + h + 6, cw, 22), name, size=16, align="c", color="muted")


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
    bw = (BODY_W - 3 * gap) / 4
    bh = 104.0
    for i, (name, what) in enumerate(blocks):
        x = LEFT + i * (bw + gap)
        d.box(x, TOP + 4, bw, bh, fill="white", line="dark", lw=1.5)
        d.text((x + 8, TOP + 12, bw - 16, 24), name, size=20, bold=True, color="dark", align="c")
        d.text((x + 8, TOP + 40, bw - 16, bh - 44), what, size=16, align="c")
        if i:
            d.line(x - gap + 3, TOP + 4 + bh / 2, x - 3, TOP + 4 + bh / 2, arrow=True)
    d.text(
        (LEFT, TOP + 116, BODY_W, 24),
        "Hardware: a laptop ({demoInferenceMachine}) and Kaggle for long runs; no headset or "
        "finger built.",
        size=18,
        color="muted",
        align="c",
    )
    cols = [
        ("path-cap", "Cap and amplifier: needed"),
        ("path-practice", "Page, server, model: built"),
        ("path-therapy", "Board, motor, finger: needed"),
    ]
    cw = BODY_W / 3
    for i, (key, label) in enumerate(cols):
        x = LEFT + i * cw
        d.picture(key, (x + 12, 262, cw - 24, 196), valign="b")
        d.text((x + 6, 466, cw - 12, 50), label, size=18, align="c", bold=i == 1)


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
    x, y, w, h = d.picture("leak-slope", (LEFT, TOP, 480, 284), align="l", valign="t")
    k = w / 365
    d.text(
        (x, y + h + 4, 150 * k, 44),
        [[*d.rich("Published way", bold=True)], "test trials used"],
        size=16,
        align="c",
    )
    d.text(
        (x + w - 170 * k, y + h + 4, 150 * k, 44),
        [[*d.rich("Leakage-free", bold=True)], "kept apart"],
        size=16,
        align="c",
    )
    rx = x + w + 24
    rw = RIGHT - rx
    rows = [
        (
            "{rqOneCspLdaReplicaPaperReplicaMean}% → {rqOneCspLdaReplicaCvLeakfreeMean}%",
            "the authors' recipe, rebuilt",
        ),
        (
            "{rqOneCspLdaPaperReplicaMean}% → {rqOneCspLdaCvLeakfreeMean}%",
            "standard CSP+LDA, pre-registered H1",
        ),
        ("{rqOneHOnePositive} of {rqOneHOneN}", "patients lower, p = {rqOneHOneP}"),
    ]
    for i, (big, small) in enumerate(rows):
        yy = TOP + 6 + i * 104
        d.text((rx, yy, rw, 32), big, size=26, bold=True, color="title")
        d.text((rx, yy + 34, rw, 56), small, size=18)
    d.text(
        (LEFT, 476, BODY_W, 44),
        "Published: {rqOnePublishedGroupBCspLda:int}–{rqOnePublishedGroupTCspLda:int}%. "
        "Leakage-free, hand and sixth finger are only weakly separable.",
        size=18,
        color="dark",
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
    cols = [LEFT, LEFT + 384, LEFT + 560]
    widths = [376, 168, RIGHT - cols[2]]
    heads = ["Study and data", "With the leak", "Leakage-free"]
    y = TOP
    for c, wdt, head in zip(cols, widths, heads, strict=True):
        d.text((c, y, wdt, 26), head, size=20, bold=True, color="dark", align="l")
    d.line(LEFT, y + 30, RIGHT, y + 30, color="dark", lw=1.25)
    rows = [
        (
            "Wang et al., 2026: published",
            "{rqOnePublishedGroupBCspLda}–{rqOnePublishedGroupTCspLda}%",
            "not reported",
        ),
        (
            "Their recipe, rebuilt by us",
            "{rqOneCspLdaReplicaPaperReplicaMean}%",
            "**{rqOneCspLdaReplicaCvLeakfreeMean}%**",
        ),
        (
            "Standard CSP+LDA, ours ({rqOneHOneN} patients)",
            "{rqOneCspLdaPaperReplicaMean}%",
            "**{rqOneCspLdaCvLeakfreeMean}%**",
        ),
        (
            "BNCI 2014-001, healthy ({rqOneBnciHOneBN})",
            "{rqOneBnciPaperReplicaMean}%",
            "**{rqOneBnciCvLeakfreeMean}%**",
        ),
        (
            "Cho 2017, healthy ({rqOneChoHOneBN})",
            "{rqOneChoPaperReplicaMean}%",
            "**{rqOneChoCvLeakfreeMean}%**",
        ),
    ]
    y += 38
    for label, leaky, clean in rows:
        for c, wdt, cell in zip(cols, widths, (label, leaky, clean), strict=True):
            d.text((c, y, wdt, 26), cell, size=20)
        d.line(LEFT, y + 32, RIGHT, y + 32, color="muted", lw=0.5)
        y += 40
    d.text(
        (LEFT, y + 14, BODY_W, 30),
        "Hand vs sixth finger for the stroke rows; left vs right hand for the healthy ones.",
        size=16,
        color="muted",
    )
    y += 58
    d.box(LEFT, y, BODY_W, 74, fill="white", line="muted", lw=1, radius=10)
    d.text(
        (LEFT + 14, y + 8, BODY_W - 28, 60),
        [
            [
                *d.rich("Healthy benchmark, exploratory:", bold=True, color="dark"),
                *d.rich(
                    " BCI Competition 2020 Track 4 (Jeong et al., 2022), {exThreeBenchPeople} "
                    "people, two grasps of one hand a week apart: "
                    "**{exThreeBenchPairsMin}–{exThreeBenchPairsMax}%**"
                ),
            ]
        ],
        size=18,
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
    x, _, w, _ = d.picture("setup", (LEFT, TOP, 566, 316), align="l", valign="t")
    rx = x + w + 18
    rw = RIGHT - rx
    d.text(
        (rx, TOP + 6, rw, 34), "{rqTwoRestAhSfRctTslrKOneMean}%", size=30, bold=True, color="title"
    )
    d.text((rx, TOP + 42, rw, 66), "with other patients, after {rqTwoMinutesKOne:sec} s", size=18)
    d.text(
        (rx, TOP + 120, rw, 34), "{rqTwoRestAhSfTsLrKOneMean}%", size=30, bold=True, color="muted"
    )
    d.text((rx, TOP + 156, rw, 66), "from scratch, same practice", size=18)
    d.text((rx, TOP + 234, rw, 66), "Guessing: one in three", size=18, color="muted")
    d.text(
        (LEFT, 438, BODY_W, 84),
        [
            "**One transfer configuration** (H2a, p = {rqTwoHTwoAP}). With all "
            "{rqTwoMinutesKAll} min, from scratch ends {rqTwoRestAhSfTsLrMinusRctTslrKAllDiff} "
            "points higher: **not tested**.",
            "Another day (exploratory): unchanged {rqFourLaterPostUnchangedMean}%; five new "
            "trials of each movement, {rqFourLaterPostRecentredKFiveMean}%.",
        ],
        size=18,
        gap=6,
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
    x, _, w, _ = d.picture("switch-patients", (LEFT, TOP, 548, 314), align="l", valign="t")
    rx = x + w + 18
    rw = RIGHT - rx
    d.text(
        (rx, TOP + 4, rw, 300),
        [
            [*d.rich("Exploratory", bold=True, color="title")],
            "Fires on **{exFourTsLrCentralFiresAhMean}%** of hand windows too",
            "Continuous: **{exFiveFingerFingerOnMean}%** of periods, "
            "{exFiveFingerFalsePerMinMean} false a minute",
            "No finger driven",
        ],
        size=18,
        gap=10,
    )
    d.text(
        (LEFT, 438, BODY_W, 84),
        [
            "**No distinct sixth-finger command** (H3, H3c inconclusive): a move-or-rest switch.",
            "Visual cues: finger vs rest best centrally ({rqFourCueSfRestCentralMean} vs "
            "{rqFourCueSfRestParietoOccipitalMean}%); hand vs finger best occipitally "
            "({rqFourCueAhSfParietoOccipitalMean} vs {rqFourCueAhSfCentralMean}%).",
        ],
        size=18,
        gap=6,
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
    d.box(LEFT, TOP, BODY_W, 168, fill="white", line="title", lw=1.5, radius=12)
    d.text(
        (LEFT + 18, TOP + 12, BODY_W - 36, 148),
        "Leakage-free, hand against sixth finger scores {rqOneCspLdaReplicaCvLeakfreeMean}–"
        "{rqOneCspLdaCvLeakfreeMean}%, not the published {rqOnePublishedGroupBCspLda:int}%; "
        "one transfer configuration lifts a new patient from {rqTwoRestAhSfTsLrKOneMean}% to "
        "{rqTwoRestAhSfRctTslrKOneMean}% after one trial of each movement, then stays flat; and "
        "the sixth finger is, so far, a **move-or-rest switch**, not a command of its own.",
        size=22,
        anchor="m",
    )
    d.text((LEFT, TOP + 188, BODY_W, 30), "Future work", size=22, bold=True, color="dark")
    d.bullets(
        (LEFT - 6, TOP + 224, BODY_W + 6, 170),
        [
            "**Closed loop**: the switch drives a real finger, with patients",
            "**Transfer that keeps learning**, e.g. a weight that grows with practice",
        ],
        size=20,
        gap=10,
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
    d.drop_body()
    rec.settings += [WINDOW, REPLAY]
    d.text((LEFT, TOP + 10, 470, 40), SITE + "/live", size=30, bold=True, color="title")
    d.text(
        (LEFT, TOP + 70, 470, 250),
        [
            "Patient **{demoSubject}**, runs the model never saw",
            "Left: the cue. Middle: the EEG. Right: the model's reading",
            "Real held-out predictions, at real speed",
        ],
        size=20,
        gap=14,
    )
    d.text(
        (LEFT, 430, 470, 60),
        f"If it does not load: {SITE_COPY}/live, or the recorded video",
        size=18,
        color="muted",
    )
    d.picture("hand-finger", (RIGHT - 240, TOP, 240, 360))


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
    d.text((tx, 336, RIGHT - tx, 40), SITE, size=26, bold=True, color="dark")
    d.text((tx, 380, RIGHT - tx, 30), " · ".join(name for name, _ in STUDENTS), size=18)
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
    """A PDF beside the deck through LibreOffice, with the template's fonts in a private profile."""
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        fonts = profile / "user" / "fonts"
        fonts.mkdir(parents=True)
        for ttf in SUPPLEMENTAL.glob("*.ttf"):
            shutil.copy(ttf, fonts)
        for ttf in (Path.home() / "Library" / "Fonts").glob("Inter-*.ttf"):
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
    """Every font in the PDF must be embedded and be one the template names."""
    out = subprocess.run(["pdffonts", str(pdf)], check=True, capture_output=True, text=True)
    problems = []
    for line in out.stdout.splitlines()[2:]:
        name = line.split()[0].split("+")[-1]
        flags = re.search(r"\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", line)
        embedded = flags.group(1) if flags else "no"
        if not name.startswith(("TimesNewRoman", "Wingdings3")):
            problems.append(f"PDF font {name} is not one of the template's")
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
        print(f"wrote {pdf.relative_to(ROOT)}, fonts embedded: Times New Roman, Wingdings 3")
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
