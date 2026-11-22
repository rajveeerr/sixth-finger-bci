"""Build the final presentation in the college's template, Sixth-Finger-BCI-Final-PPT.pptx.

uv run --with python-pptx==1.0.2 --with fonttools python report/slides/college/build_college_ppt.py
uv run --with python-pptx==1.0.2 --with fonttools \
    python report/slides/college/build_college_ppt.py --pdf --previews

The deck starts from a copy of the college's "Final PPT.pptx" and keeps its slide order and
section titles: title, contents, introduction, proposed solution, dataset, experimental details,
results, conclusion, questions, thank you. Its master is redrawn: a warm near-white field, a navy
band along the top, a footer with the project, the college and the slide number, and a title
slide and closing slides built around the MSIT logo on a navy panel. All text is Inter (fonts/,
SIL Open Font License), embedded in the .pptx so PowerPoint shows it on a PC without it, and in
the PDF. Numbers come from paper/generated/numbers.tex through the macros of ../build_slides.py,
written in the slide text as {macroName}; the speaker notes give each one with its results file.
The build fails on text under 16 pt, text that does not fit its box, a figure whose smallest
text would print under 16 pt, a digit typed by hand, a talk that is not 15:00, or (with --pdf) a
PDF or embedded-font check that does not pass.

The deck carries the students' enrolment numbers: it is not copied to the website.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import re
import shutil
import struct
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
from fontTools.ttLib import TTFont
from lxml import etree
from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Pt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_slides as bs  # noqa: E402

ROOT = bs.ROOT
OUT = HERE / "Sixth-Finger-BCI-Final-PPT.pptx"
PREVIEWS = HERE / "previews"
FONTS = HERE / "fonts"
TEMPLATE = Path.home() / "Downloads" / "Final PPT.pptx"
SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")

# The slide in points, and the frame every content slide keeps: the title under the navy band,
# content between the title and the footer rule.
W, H = 960.0, 540.0
CL, CR = 48.0, 912.0
CW = CR - CL
CT, CB = 100.0, 486.0
BAND_H = 8.0
TITLE_BOX = (CL, 30.0, CW, 48.0)
FOOT_RULE, FOOT_Y = 498.0, 506.0
MIN_PT = 16.0
TALK_SECONDS = 15 * 60
DEMO_SECONDS = 3 * 60
MAX_BYTES = 5_000_000

# Type: Inter throughout. Regular for text, SemiBold for labels and emphasis, Bold for titles
# and key numbers (a bold span at HEAVY_PT or more).
FACE, FACE_SEMI = "Inter", "Inter SemiBold"
FONT_FILES = {
    "regular": "Inter-Regular.ttf",
    "semibold": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
}
# What the .pptx embeds: typeface, slot, file. SemiBold is its own family to Windows.
EMBED = [
    (FACE, "regular", "regular"),
    (FACE, "bold", "bold"),
    (FACE_SEMI, "regular", "semibold"),
]
TITLE_PT = 30.0
STAT_PT = 40.0
LEAD_PT = 22.0
BODY_PT = 20.0
SMALL_PT = 18.0
CAPTION_PT = 16.0
HEAVY_PT = 24.0

# Colour: a warm near-white field, the template's navy deepened for the band and titles, a
# deeper cut of its blue, and the MSIT logo's red and gold. Every text colour keeps at least
# 4.5:1 on the field, on white and on cream.
PALETTE = {
    "field": "F6F5F1",
    "ink": "1F2933",
    "navy": "22405A",
    "blue": "105C82",
    "red": "A93220",
    "gold": "E3A81B",
    "cream": "FCF1D2",
    "muted": "56606B",
    "line": "D9D5CB",
    "pale": "EFEDE7",
    "white": "FFFFFF",
    "sky": "B9D3E4",
}

STUDENTS = [
    ("Rajveer Singh", "05096302823"),
    ("Vivek Yadav", "05196302823"),
    ("Ansh Dahiya", "35396302823"),
]
GUIDE = ["Dr. Suman Lata", "Assistant Professor", "Department of ECE, MSIT"]
TOPIC = "EEG-Based Adaptive Brain–Computer Interface for Novel Artificial Limb Control"
FOOTER = ("Sixth-Finger BCI", "MSIT")
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

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
XMLNS = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())


def rgb(name: str) -> RGBColor:
    return RGBColor.from_string(PALETTE[name])


def emu(pt: float) -> int:
    return round(pt * 12700)


def weight(bold: bool, size: float) -> str:
    if not bold:
        return "regular"
    return "bold" if size >= HEAVY_PT else "semibold"


# Text measurement with the deck's own font


class Measure:
    """Widths and line height of Inter, read from the font files."""

    def __init__(self) -> None:
        self.fonts = {k: ImageFont.truetype(str(FONTS / f), 1000) for k, f in FONT_FILES.items()}
        ascent, descent = self.fonts["regular"].getmetrics()
        # Both PowerPoint and LibreOffice set single spacing at ascent + descent for Inter.
        self.line = (ascent + descent) / 1000 * 1.02

    def width(self, text: str, size: float, bold: bool) -> float:
        return self.fonts[weight(bold, size)].getlength(text) * size / 1000

    def lines(self, spans: list[bs.Span], width: float, size: float) -> int:
        words: list[tuple[str, float, bool]] = []
        for sp in spans:
            sz = (sp.size or size) * (0.6 if sp.sup else 1)
            for word in re.split(r"(\s+)", sp.text):
                if word:
                    words.append((word, sz, bool(sp.bold)))
        lines, used = 1, 0.0
        # A point of slack for kerning and hinting differences between renderers.
        room = width - 1
        for word, sz, b in words:
            w = self.width(word, sz, b)
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


# Embedded fonts


def eot(ttf: bytes) -> bytes:
    """The font wrapped as Embedded OpenType 2.2, uncompressed, as PowerPoint's .fntdata holds."""
    font = TTFont(io.BytesIO(ttf))
    os2, name = font["OS/2"], font["name"]
    p = os2.panose
    panose = bytes(
        [
            p.bFamilyType,
            p.bSerifStyle,
            p.bWeight,
            p.bProportion,
            p.bContrast,
            p.bStrokeVariation,
            p.bArmStyle,
            p.bLetterForm,
            p.bMidline,
            p.bXHeight,
        ]
    )
    head = panose + struct.pack(
        "<BBIHH4I2II4I",
        0,
        1 if os2.fsSelection & 1 else 0,
        os2.usWeightClass,
        os2.fsType,
        0x504C,
        os2.ulUnicodeRange1,
        os2.ulUnicodeRange2,
        os2.ulUnicodeRange3,
        os2.ulUnicodeRange4,
        os2.ulCodePageRange1,
        os2.ulCodePageRange2,
        font["head"].checkSumAdjustment,
        0,
        0,
        0,
        0,
    )
    for name_id in (1, 2, 5, 4):
        text = (str(name.getName(name_id, 3, 1, 0x409)) + "\0").encode("utf-16-le")
        head += struct.pack("<HH", 0, len(text)) + text
    # An empty root string, its checksum, code page 1252, no signature and no EUDC font.
    head += struct.pack("<HH", 0, 0) + struct.pack("<IIHHII", 0x50475342, 1252, 0, 0, 0, 0)
    fixed = struct.pack("<IIII", 16 + len(head) + len(ttf), len(ttf), 0x00020002, 0)
    return fixed + head + ttf


def renamed_font(ttf: bytes, old: str, new: str) -> bytes:
    """The same font under another family name, for the embedding check."""
    font = TTFont(io.BytesIO(ttf))
    for record in font["name"].names:
        if record.nameID in (1, 3, 4, 6, 16):
            text = record.toUnicode()
            text = text.replace(old, new) if record.nameID != 6 else text.replace("Inter", new)
            record.string = text
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def panose_of(file: str) -> str:
    p = TTFont(str(FONTS / file))["OS/2"].panose
    return "".join(
        f"{v:02X}"
        for v in (
            p.bFamilyType,
            p.bSerifStyle,
            p.bWeight,
            p.bProportion,
            p.bContrast,
            p.bStrokeVariation,
            p.bArmStyle,
            p.bLetterForm,
            p.bMidline,
            p.bXHeight,
        )
    )


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
    """The figure cropped, with its paper taken out so it sits on any card."""
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


# Master, layouts and backgrounds


def _sp(shape_id: int, name: str, box: tuple[float, float, float, float], body: str) -> Any:
    x, y, w, h = box
    return parse_xml(
        f'<p:sp {XMLNS}><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvSpPr/>'
        f'<p:nvPr userDrawn="1"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/>'
        f'<a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
        f"</a:prstGeom>{body}</p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p>"
        '<a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
    )


def _fill(colour: str) -> str:
    return (
        f'<a:solidFill><a:srgbClr val="{PALETTE[colour]}"/></a:solidFill><a:ln><a:noFill/></a:ln>'
    )


def _label(shape_id: int, name: str, box: tuple[float, float, float, float], text: str) -> Any:
    x, y, w, h = box
    return parse_xml(
        f'<p:sp {XMLNS}><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr userDrawn="1"/></p:nvSpPr><p:spPr><a:xfrm>'
        f'<a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody>'
        '<a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t"/><a:lstStyle/>'
        '<a:p><a:r><a:rPr lang="en-US" sz="1600"><a:solidFill>'
        f'<a:srgbClr val="{PALETTE["muted"]}"/></a:solidFill><a:latin typeface="{FACE}"/>'
        f"</a:rPr><a:t>{text}</a:t></a:r></a:p>"
        "</p:txBody></p:sp>"
    )


def _drop_decoration(tree: Any) -> None:
    """Everything on a master or layout that is not a placeholder: the curves and the arrow."""
    for el in list(tree):
        tag = etree.QName(el).localname
        loose = tag == "sp" and el.find(".//p:nvPr/p:ph", NS) is None
        if loose or tag in ("grpSp", "pic", "cxnSp", "graphicFrame"):
            tree.remove(el)


def _set_background(c_sld: Any, colour: str | None) -> None:
    for bg in c_sld.findall("p:bg", NS):
        c_sld.remove(bg)
    if colour:
        bg = parse_xml(
            f'<p:bg {XMLNS}><p:bgPr><a:solidFill><a:srgbClr val="{PALETTE[colour]}"/>'
            "</a:solidFill><a:effectLst/></p:bgPr></p:bg>"
        )
        c_sld.insert(0, bg)


def _text_style(level: Any, size: float, colour: str, face: str, bold: bool = False) -> None:
    rpr = level.find("a:defRPr", NS)
    rpr.set("sz", str(round(size * 100)))
    rpr.set("b", "1" if bold else "0")
    fills = ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
    for child in list(rpr):
        if etree.QName(child).localname in (*fills, "latin"):
            rpr.remove(child)
    # Schema order: ln, then the fill, then effects; latin before ea, cs and the rest.
    fill = etree.Element(qn("a:solidFill"))
    etree.SubElement(fill, qn("a:srgbClr"), val=PALETTE[colour])
    ln = rpr.find("a:ln", NS)
    rpr.insert(0 if ln is None else list(rpr).index(ln) + 1, fill)
    latin = etree.Element(qn("a:latin"), typeface=face)
    after = ("ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst")
    nxt = next((c for c in rpr if etree.QName(c).localname in after), None)
    if nxt is None:
        rpr.append(latin)
    else:
        nxt.addprevious(latin)


def redraw_master(prs: Presentation) -> None:
    """The template's master and layouts with its curves and arrow taken out and the deck's own
    field, band and footer put in; the title slide's layout shows none of them."""
    master = prs.slide_master
    tree = master.shapes._spTree
    _drop_decoration(tree)
    _set_background(master._element.find("p:cSld", NS), "field")
    rule = FOOT_RULE
    divider_x = CL + Measure().width(FOOTER[0], CAPTION_PT, False) + 12
    for el in (
        _sp(9001, "Top band", (0, 0, W, BAND_H), _fill("navy")),
        _sp(9002, "Footer rule", (CL, rule, CW, 0.75), _fill("line")),
        _label(9003, "Footer project", (CL, FOOT_Y, 200, 20), FOOTER[0]),
        _sp(9004, "Footer divider", (divider_x, FOOT_Y + 2, 0.75, 15), _fill("line")),
        _label(9005, "Footer college", (divider_x + 12, FOOT_Y, 80, 20), FOOTER[1]),
    ):
        tree.append(el)
    for ph in master.placeholders:
        kind = ph.placeholder_format.type
        if kind == 13:  # slide number, at the footer's right
            ph.left, ph.top, ph.width, ph.height = Pt(CR - 100), Pt(FOOT_Y), Pt(100), Pt(20)
            body = ph.text_frame._txBody.find(qn("a:bodyPr"))
            for side in ("lIns", "tIns", "rIns", "bIns"):
                body.set(side, "0")
            body.set("anchor", "t")
            level = ph.text_frame._txBody.find("a:lstStyle/a:lvl1pPr", NS)
            if level is not None:
                _text_style(level, CAPTION_PT, "navy", FACE_SEMI)
        elif kind == 1:  # title
            x, y, w, h = TITLE_BOX
            ph.left, ph.top, ph.width, ph.height = Pt(x), Pt(y), Pt(w), Pt(h)
    styles = master._element.find("p:txStyles", NS)
    _text_style(styles.find("p:titleStyle/a:lvl1pPr", NS), TITLE_PT, "navy", "+mj-lt", True)
    for level in styles.find("p:bodyStyle", NS):
        if etree.QName(level).localname.startswith("lvl"):
            _text_style(level, BODY_PT, "ink", "+mn-lt")
            for bu in level.findall("a:buFont", NS):
                bu.set("typeface", FACE)
                bu.attrib.pop("charset", None)
                bu.attrib.pop("panose", None)
                bu.attrib.pop("pitchFamily", None)
            for bu in level.findall("a:buChar", NS):
                bu.set("char", "▪")
            for clr in level.findall("a:buClr", NS):
                for child in list(clr):
                    clr.remove(child)
                etree.SubElement(clr, qn("a:srgbClr"), val=PALETTE["blue"])
    for layout in prs.slide_layouts:
        _drop_decoration(layout.shapes._spTree)
        _set_background(layout._element.find("p:cSld", NS), None)
        if layout.name == "Title Slide":
            layout._element.set("showMasterSp", "0")
    part = master.part.part_related_by(RT.THEME)
    xml = part.blob.decode("utf-8")
    for kind in ("majorFont", "minorFont"):
        xml = re.sub(
            rf"(<a:{kind}><a:latin typeface=\")[^\"]*(\")[^/]*/>",
            rf'\g<1>{FACE}\g<2> panose="{panose_of(FONT_FILES["regular"])}"/>',
            xml,
        )
    part._blob = xml.encode("utf-8")


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
    chrome: bool = True


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
        redraw_master(self.prs)
        for s in self.template:
            _set_background(s._element.find("p:cSld", NS), None)
        logo = next(sh for sh in self.template[0].shapes if sh.shape_type == 13)
        self.logo = logo.image.blob

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
    def _font(f: Any, bold: bool, size: float) -> None:
        kind = weight(bold, size)
        f.name = FACE_SEMI if kind == "semibold" else FACE
        f.bold = kind == "bold"

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
            sz = sp.size or size
            self._font(f, bool(sp.bold) or bool(nums and sp.macro), sz)
            f.size = Pt(sz)
            f.italic = False
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
        nums: str | None = None,
    ) -> Any:
        """A text box without insets; nums colours (and bolds) the macro numbers in it."""
        x, y, w, h = box
        if isinstance(paras, str):
            paras = [paras]
        resolved = self._paras(paras, bold)
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
        """Bullets in the layout's body placeholder: a small square, the text hung beside it."""
        x, y, w, h = box
        indent = round(size * 1.1)
        ph = self._body()
        tree = ph._element.getparent()
        tree.remove(ph._element)
        tree.append(ph._element)
        ph.left, ph.top, ph.width, ph.height = Pt(x), Pt(y), Pt(w), Pt(h)
        tf = ph.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, side, 0)
        tf.vertical_anchor = MSO_ANCHOR.TOP
        body = tf._txBody.find(qn("a:bodyPr"))
        for fit in list(body):
            body.remove(fit)
        tf.text = ""
        resolved = self._paras(items, False)
        for i, spans in enumerate(resolved):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(gap if i else 0)
            p.line_spacing = 1.0
            self._runs(p, spans, size, color, nums)
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", str(emu(indent)))
            ppr.set("indent", str(-emu(indent)))
            clr = etree.SubElement(ppr, qn("a:buClr"))
            etree.SubElement(clr, qn("a:srgbClr"), val=PALETTE[mark])
            etree.SubElement(ppr, qn("a:buSzPct"), val="80000")
            etree.SubElement(ppr, qn("a:buFont"), typeface=FACE)
            etree.SubElement(ppr, qn("a:buChar"), char="▪")
        self.boxes.append(TextBox(self.rec.no, resolved, size, w - indent, h, gap))
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
        """A content slide: one of the template's own, or a new one from its layout.

        The title's section ("Results:") is set in blue, the rest in navy.
        """
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
            tf.word_wrap = True
            for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                setattr(tf, side, 0)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.text = ""
            spans = self.rich(title, bold=True)
            head = "".join(sp.text for sp in spans)
            section, colon, rest = head.partition(": ")
            parts = [(section + colon, "blue"), (rest, "navy")] if colon else [(head, "navy")]
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            for text, colour in parts:
                r = p.add_run()
                r.text = text
                self._font(r.font, True, TITLE_PT)
                r.font.size = Pt(TITLE_PT)
                r.font.color.rgb = rgb(colour)
            self.boxes.append(TextBox(rec.no, [spans], TITLE_PT, w, h, 0))
            rec.title = head
        else:
            rec.title = s.shapes.title.text_frame.text
        rec.say = self.plain(say)
        return rec

    def keep(self, index: int, seconds: int, say: str, part: str = "talk") -> Record:
        """One of the template's slides, its own text kept, with notes."""
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
        self.text((x + 20, y + 6, w - 32, h - 12), paras, size=size, anchor="m", nums=nums, gap=gap)

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
        """A figure on a white card fitted to it (or as wide as the box, if wide); below leaves
        room for a caption inside the card. Returns the picture's box and the card's box."""
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

    def panel(self) -> None:
        """The navy panel with the MSIT logo on a white card: the title and closing slides."""
        self.rec.chrome = False
        self.rec.slide._element.set("showMasterSp", "0")
        self.box(0, 0, 320, H, fill="navy", line=None, radius=0)
        cw, ch = 196.0, 184.0
        cx, cy = (320 - cw) / 2, (H - ch) / 2
        self.box(cx, cy, cw, ch, fill="white", line=None, radius=14)
        self.box(cx + cw / 2 - 28, cy + ch + 26, 56, 4, fill="gold", line=None, radius=0)
        lw = cw - 36
        lh = lw * 114.5 / 123.0
        self.rec.slide.shapes.add_picture(
            io.BytesIO(self.logo), Pt(cx + 18), Pt(cy + (ch - lh) / 2), Pt(lw), Pt(lh)
        )

    def number_slide(self, rec: Record) -> None:
        """The slide number, in the footer's place on the master."""
        tree = rec.slide.shapes._spTree
        new_id = max(int(e.get("id")) for e in tree.iter(qn("p:cNvPr"))) + 1
        sp = parse_xml(
            f"<p:sp {XMLNS}><p:nvSpPr>"
            f'<p:cNvPr id="{new_id}" name="Slide Number"/><p:cNvSpPr>'
            '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldNum" sz="quarter" '
            'idx="12"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>'
            '<a:pPr algn="r"/><a:fld id="{69E57DC2-970A-4B3E-BB1C-7A09969E49DF}" type="slidenum">'
            f'<a:rPr lang="en-US" sz="1600" b="0"><a:solidFill><a:srgbClr val="{PALETTE["navy"]}"/>'
            f'</a:solidFill><a:latin typeface="{FACE_SEMI}"/></a:rPr>'
            f"<a:t>{rec.no}</a:t></a:fld></a:p></p:txBody></p:sp>"
        )
        tree.append(sp)

    def retype(self) -> None:
        """Whatever the template's own runs still name, in Inter."""
        for rec in self.records:
            for el in rec.slide._element.iter(
                qn("a:latin"), qn("a:ea"), qn("a:cs"), qn("a:buFont")
            ):
                face = el.get("typeface", "")
                if face and not face.startswith(("Inter", "+")):
                    el.set("typeface", FACE)
                    for attr in ("panose", "pitchFamily", "charset"):
                        el.attrib.pop(attr, None)

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


def _refill(d: Deck, shape: Any, paras: list[list[bs.Span]], gap: float = 0) -> None:
    """A template text shape emptied and filled again, its insets and autofit taken off."""
    tf = shape.text_frame
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.word_wrap = True
    body = tf._txBody.find(qn("a:bodyPr"))
    for fit in list(body):
        body.remove(fit)
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.text = ""
    for i, spans in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_before = Pt(gap if i else 0)
        p.line_spacing = 1.0
        ppr = p._p.get_or_add_pPr()
        ppr.set("marL", "0")
        ppr.set("indent", "0")
        etree.SubElement(ppr, qn("a:buNone"))
        for sp in spans:
            r = p.add_run()
            r.text = sp.text
            d._font(r.font, bool(sp.bold), sp.size)
            r.font.size = Pt(sp.size)
            r.font.color.rgb = rgb(sp.color)
    w, h = shape.width / 12700, shape.height / 12700
    d.boxes.append(TextBox(d.rec.no, paras, paras[-1][0].size, w, h, gap))


def _place(shape: Any, box: tuple[float, float, float, float]) -> None:
    x, y, w, h = box
    shape.left, shape.top, shape.width, shape.height = Pt(x), Pt(y), Pt(w), Pt(h)


# The right-hand side of the title and closing slides, beside the navy panel.
PANEL_X = 376.0


def title_slide(d: Deck) -> None:
    rec = d.keep(
        0,
        30,
        "Good morning. We are Rajveer Singh, Vivek Yadav and Ansh Dahiya, and our minor project, "
        "guided by Dr. Suman Lata, asks whether a stroke patient's brain signals can control a "
        "robotic sixth finger, and how quickly such a system can be set up for a new patient.",
    )
    shapes = list(rec.slide.shapes)
    heading, by_hand, topic, guide, logo = shapes[:5]
    logo._element.getparent().remove(logo._element)
    d.panel()
    rw = CR - PANEL_X

    _place(heading, (PANEL_X, 96, rw, 26))
    _refill(
        d,
        heading,
        [[bs.Span("Minor Project presentation", bold=True, size=SMALL_PT, color="blue")]],
    )
    _place(topic, (PANEL_X, 128, rw, 130))
    _refill(d, topic, [[bs.Span(TOPIC, bold=True, size=32, color="navy")]])
    d.box(PANEL_X, 276, 56, 4, fill="gold", line=None, radius=0)

    label = {"bold": True, "size": CAPTION_PT, "color": "muted"}
    col = 268.0
    _place(by_hand, (PANEL_X, 304, col, 190))
    names = [[bs.Span("By:", **label)]]
    for name, number in STUDENTS:
        names.append([bs.Span(name, bold=True, size=BODY_PT, color="ink")])
        names.append([bs.Span(number, size=CAPTION_PT, color="muted", free=True)])
    _refill(d, by_hand, names, gap=3)
    for i, p in enumerate(by_hand.text_frame.paragraphs):
        if i and i % 2 == 1:
            p.space_before = Pt(10)

    _place(guide, (PANEL_X + col + 16, 304, rw - col - 16, 190))
    paras = [[bs.Span("Under the guidance of:", **label)]]
    paras.append([bs.Span(GUIDE[0], bold=True, size=BODY_PT, color="ink")])
    paras += [[bs.Span(line, size=SMALL_PT, color="ink")] for line in GUIDE[1:]]
    _refill(d, guide, paras, gap=6)
    guide.text_frame.paragraphs[1].space_before = Pt(10)
    rec.drawn.append(
        "The enrolment numbers on this slide are why this deck never goes on the website."
    )


def contents_slide(d: Deck) -> None:
    rec = d.slide(
        d.template[1].shapes.title.text_frame.text,
        10,
        "The talk follows the college's order: why the problem matters, what we did, the data, "
        "how we did it, what we found, and what it means; the live demo comes just before "
        "questions.",
        reuse=1,
    )
    body = next(s for s in rec.slide.placeholders if s.placeholder_format.idx == 1)
    items = [p.text.strip() for p in body.text_frame.paragraphs if p.text.strip()]
    d.drop_body()
    colw, gap, rh = 404.0, 56.0, 76.0
    for i, item in enumerate(items):
        col, row = divmod(i, 4)
        x, y = CL + col * (colw + gap), CT + 14 + row * rh
        d.line(x, y, x + colw, y, color="line", lw=0.75)
        d.text(
            (x, y + 16, 56, 40),
            [[bs.Span(f"{i + 1:02d}", bold=True, free=True)]],
            size=28,
            color="blue",
        )
        d.text((x + 64, y + 20, colw - 64, 30), item, size=LEAD_PT, bold=True, color="navy")


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
        (CL, CT + 34, 352, 300),
        [
            "**Stroke** often leaves one hand too weak to grip",
            "A **robotic sixth finger**, worn on that wrist, grips against the palm",
            "Aim: the patient **imagines** moving it, and it moves",
        ],
        size=LEAD_PT,
        gap=24,
    )
    cw, gap = 234.0, 18.0
    x0 = CR - 2 * cw - gap
    for i, (key, label) in enumerate([("hand-rest", "at rest"), ("hand-finger", "bent to grip")]):
        x = x0 + i * (cw + gap)
        _, (_, cy, _, ch) = d.framed(key, (x, CT, cw, 340), pad=16, below=34)
        d.text((x, cy + ch - 38, cw, 24), label, size=SMALL_PT, align="c", color="muted")
    d.text(
        (CL, 446, CW, 40),
        "BCI therapy after stroke: Cervera et al., 2018. Extra robotic fingers: "
        "Prattichizzo et al., 2021; Kieliba et al., 2021.",
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
        "system", (CL, CT, CW, 306), pad=14, below=40, wide=True
    )
    crop = FIGS["system"].crop or (0, 0, 0, 0)
    k = w / (crop[2] - crop[0])
    # The drawing's own numbers print small; larger ones are laid over them.
    centres = [(461, 382), (741, 434), (1039, 489), (1609.5, 593), (1820.5, 631)]
    for i, (px, py) in enumerate(centres, start=1):
        d.badge(x + (px - crop[0]) * k, y + (py - crop[1]) * k, str(i), r=13)
    names = ["EEG cap", "Amplifier", "<<4 s>> of signal", "Model", "Robotic finger"]
    colw = (cw0 - 28) / len(names)
    for i, name in enumerate(names, start=1):
        spans = [bs.Span(f"{i}  ", bold=True, free=True, color="blue"), *d.rich(name)]
        d.text(
            (cx0 + 14 + (i - 1) * colw, cy + ch - 36, colw, 26), [spans], size=SMALL_PT, align="c"
        )
    d.band(
        (CL, cy + ch + 14, CW, CB - cy - ch - 14),
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
    gap = 24.0
    half = (CW - gap) / 2
    top, height = CT, 314.0
    d.box(CL, top, half, height)
    d.box(CL, top, half, 5, fill="red", line=None, radius=0)
    d.text(
        (CL + 22, top + 20, half - 44, 28),
        "Problem statement",
        size=LEAD_PT,
        bold=True,
        color="navy",
    )
    d.text(
        (CL + 22, top + 56, half - 44, 60),
        "{rqOnePublishedGroupBCspLda:int}–{rqOnePublishedGroupTCspLda:int}%",
        size=48,
        bold=True,
        color="red",
    )
    d.text(
        (CL + 22, top + 118, half - 44, 24),
        "Published, hand vs sixth finger",
        size=SMALL_PT,
        color="muted",
    )
    d.bullets(
        (CL + 22, top + 164, half - 44, 140),
        [
            "But its filters also saw the **test trials**",
            "Every user must first **calibrate**: effort for a patient",
        ],
        size=BODY_PT,
        gap=12,
        mark="red",
    )
    x2 = CL + half + gap
    d.box(x2, top, half, height)
    d.box(x2, top, half, 5, fill="blue", line=None, radius=0)
    d.text((x2 + 22, top + 20, half - 44, 28), "Objectives", size=LEAD_PT, bold=True, color="navy")
    objectives = [
        "Re-test the dataset **leakage-free**",
        "Measure calibration, with and without **other patients**",
        "Test the sixth finger as a **command of its own**",
        "Build a **demonstrator** on held-out data",
    ]
    y = top + 66
    for i, item in enumerate(objectives, start=1):
        paras = d._paras([item], False)
        need = d.height(paras, half - 84, BODY_PT, 0)
        d.badge(x2 + 35, y + 12, str(i), r=12, fill="blue")
        d.text((x2 + 60, y, half - 82, need + 2), paras, size=BODY_PT)
        y += max(need, 26) + 16
    d.band(
        (CL, top + height + 12, CW, CB - top - height - 12),
        [
            [
                *d.rich("Significance   ", bold=True, color="navy"),
                *d.rich(
                    "Shorter set-up for rehabilitation BCIs, and an honest baseline for everyone "
                    "who uses this public dataset."
                ),
            ]
        ],
        size=SMALL_PT + 1,
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
    gap = 34.0
    bw = (CW - 3 * gap) / 4
    bh = 122.0
    rows = [CT + 14, CT + 14 + bh + 62]
    places = []
    for i in range(8):
        row = i // 4
        col = i % 4 if row == 0 else 3 - i % 4
        places.append((CL + col * (bw + gap), rows[row]))
    for i, ((name, what, dashed), (x, y)) in enumerate(zip(stages, places, strict=True)):
        d.box(x, y, bw, bh, line="muted" if dashed else "navy", lw=1.25, dash=dashed)
        # The stage number sits on the card's top edge, leaving the name the full width.
        d.badge(x + 30, y, str(i + 1), r=13, fill="muted" if dashed else "navy")
        d.text((x + 18, y + 24, bw - 34, 28), name, size=BODY_PT, bold=True, color="navy")
        d.text((x + 18, y + 58, bw - 34, bh - 64), what, size=SMALL_PT)
    for i in range(7):
        (x1, y1), (x2, y2) = places[i], places[i + 1]
        if y1 == y2:
            if x2 > x1:
                d.line(x1 + bw + 5, y1 + bh / 2, x2 - 5, y2 + bh / 2, arrow=True)
            else:
                d.line(x1 - 5, y1 + bh / 2, x2 + bw + 5, y2 + bh / 2, arrow=True)
        else:
            d.line(x1 + bw / 2, y1 + bh + 5, x2 + bw / 2, y2 - 17, arrow=True)
    ly = 456.0
    d.box(CL, ly + 2, 30, 18, line="navy", lw=1.25, radius=3)
    d.text(
        (CL + 42, ly, 360, 24),
        "Solid: pre-registered tests and the system.",
        size=CAPTION_PT,
        color="muted",
    )
    d.box(CL + 420, ly + 2, 30, 18, line="muted", lw=1.25, dash=True, radius=3)
    d.text(
        (CL + 462, ly, CW - 462, 24),
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
    _, (cx, cy, cw, ch) = d.framed("leak", (CL, CT - 4, 600, 345), pad=4)
    rx = cx + cw + 28
    rw = CR - rx
    items = [
        ("Leakage-free", "every step learns from training trials only"),
        ("Learn", "on runs 1–2"),
        ("Test", "on runs 3–4, never seen"),
        ("Pre-registered", "tests fixed before they ran"),
    ]
    y = cy + 6
    for i, (head, what) in enumerate(items):
        if i:
            d.line(rx, y - 10, CR, y - 10, color="line", lw=0.75)
        paras = [d.rich(head, bold=True, color="blue"), d.rich(what)]
        need = d.height(paras, rw, SMALL_PT + 1, 3)
        d.text((rx, y, rw, need + 2), paras, size=SMALL_PT + 1, gap=3)
        y += need + 22
    d.band(
        (CL, cy + ch + 10, CW, CB - cy - ch - 10),
        "The two differ only in what the first step learns from.",
        size=SMALL_PT,
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
    left = 436.0
    d.text((CL, CT - 6, 96, 72), "{nSubjects}", size=56, bold=True, color="blue")
    d.text(
        (CL + 96, CT + 6, left - 96, 52),
        [d.rich("stroke patients", bold=True, color="navy"), d.rich("we recorded no one")],
        size=BODY_PT,
    )
    d.bullets(
        (CL, CT + 82, left, 170),
        [
            "**Wang et al., 2026**, on figshare, CC BY 4.0",
            "<<40>> EEG channels at {nSamplingRate} Hz, preprocessed",
            "Imagine: grasp with the **hand**, or flex the **sixth finger**",
        ],
        size=BODY_PT,
        gap=12,
    )
    x2 = CL + left + 28
    bw = CR - x2
    top, bh = CT, 236.0
    d.box(x2, top, bw, bh)
    d.box(x2, top, bw, 5, fill="red", line=None, radius=0)
    d.text(
        (x2 + 20, top + 18, bw - 40, 26), "Problems we found", size=BODY_PT, bold=True, color="red"
    )
    d.text(
        (x2 + 20, top + 52, bw - 40, 110),
        [
            "A follow-up session copied from another",
            "sub-21 and sub-22 share one recording",
            "One run with no imagery",
        ],
        size=SMALL_PT,
        gap=8,
    )
    d.line(x2 + 20, top + 170, x2 + bw - 20, top + 170, color="line", lw=0.75)
    d.text(
        (x2 + 20, top + 182, bw - 40, 46),
        "Kept: **{nRunsKept} runs**, **{nPre} patients** before therapy",
        size=SMALL_PT,
        nums="blue",
    )
    # The session design as the page's session.png draws it, in the deck's colours.
    y0 = 356.0
    sessions = ["Before therapy", "After two weeks", "A month later"]
    sgap = 48.0
    sw = (CW - 2 * sgap) / 3
    for i, name in enumerate(sessions):
        x = CL + i * (sw + sgap)
        d.box(x, y0, sw, 64, fill="navy", line=None, radius=8)
        d.text(
            (x + 8, y0 + 8, sw - 16, 48),
            [
                [*d.rich(f"Session <<{i + 1}>>", bold=True, color="white")],
                [*d.rich(name, color="sky")],
            ],
            size=SMALL_PT,
            align="c",
            color="white",
        )
        if i:
            d.line(x - sgap + 8, y0 + 32, x - 8, y0 + 32, arrow=True)
    d.text(
        (CL, y0 + 82, CW, 46),
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
    name_w = 226.0
    y = CT - 2
    for i, (name, what) in enumerate(methods):
        paras = d._paras([what], False)
        need = max(d.height(paras, CW - name_w, SMALL_PT + 1, 0), 24)
        if i:
            d.line(CL, y - 8, CR, y - 8, color="line", lw=0.75)
        d.text((CL, y, name_w, need + 2), name, size=SMALL_PT + 1, bold=True, color="navy")
        d.text((CL + name_w, y, CW - name_w, need + 2), paras, size=SMALL_PT + 1)
        y += need + 16
    y += 6
    d.box(CL, y, CW, CB - y)
    d.text(
        (CL + 20, y + 14, CW - 40, 38),
        [
            [
                *d.rich("EEGNet in the demo      ", bold=True, color="navy"),
                *d.rich("{demoParameters}", bold=True, color="blue", size=30),
                *d.rich("  learned numbers      "),
                *d.rich("{demoModelKb} KB", bold=True, color="blue", size=30),
                *d.rich("      runs in the browser"),
            ]
        ],
        size=SMALL_PT,
    )
    x, py, w, h = d.picture("model", (CL + 20, y + 60, CW - 40, CB - y - 94), valign="t")
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
    gap = 34.0
    bw = (CW - 3 * gap) / 4
    bh = 112.0
    top = CT - 2
    for i, (name, what) in enumerate(blocks):
        x = CL + i * (bw + gap)
        d.box(x, top, bw, bh, line="navy", lw=1.25)
        d.box(x, top, bw, 36, fill="navy", line=None, radius=6)
        d.box(x, top + 28, bw, 8, fill="navy", line=None, radius=0)
        d.text(
            (x + 6, top + 7, bw - 12, 24), name, size=SMALL_PT, bold=True, color="white", align="c"
        )
        d.text((x + 12, top + 46, bw - 24, bh - 50), what, size=CAPTION_PT, align="c")
        if i:
            d.line(x - gap + 5, top + bh / 2 + 12, x - 5, top + bh / 2 + 12, arrow=True)
    d.text(
        (CL, top + bh + 12, CW, 24),
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
    cgap = 24.0
    colw = (CW - 2 * cgap) / 3
    ytop = top + bh + 50
    for i, (key, label, built) in enumerate(cols):
        x = CL + i * (colw + cgap)
        d.box(
            x,
            ytop,
            colw,
            CB - ytop,
            line="blue" if built else "muted",
            lw=2 if built else 1,
            dash=not built,
        )
        d.picture(key, (x + 16, ytop + 12, colw - 32, CB - ytop - 58), valign="b")
        d.text(
            (x + 8, CB - 42, colw - 16, 30),
            label,
            size=SMALL_PT,
            align="c",
            anchor="m",
            bold=built,
            color="blue" if built else "ink",
        )


def _stat(
    d: Deck,
    x: float,
    y: float,
    w: float,
    big: list,
    caption: str | list,
    size: float,
    color: str = "blue",
    caption_color: str = "muted",
) -> float:
    """A key number with its caption under it; returns the height used."""
    d.text((x, y, w, size * 1.3), [big], size=size, bold=True, color=color)
    paras = d._paras(caption if isinstance(caption, list) else [caption], False)
    need = d.height(paras, w, 17, 0)
    d.text((x, y + size * 1.3, w, need + 2), paras, size=17, color=caption_color)
    return size * 1.3 + need


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
    (x, y, w, h), (cx, cy, cw, ch) = d.framed(
        "leak-slope", (CL, CT - 4, 524, CB - CT + 4), pad=10, below=46
    )
    k = w / 365
    d.text(
        (x, y + h + 4, 150 * k, 40),
        [[*d.rich("Published way", bold=True, color="red")], "test trials used"],
        size=CAPTION_PT,
        align="c",
    )
    d.text(
        (x + w - 170 * k, y + h + 4, 150 * k, 40),
        [[*d.rich("Leakage-free", bold=True, color="blue")], "kept apart"],
        size=CAPTION_PT,
        align="c",
    )
    rx = cx + cw + 32
    rw = CR - rx
    yy = cy + 4
    for before, after, what in [
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
    ]:
        big = [
            *d.rich(before, bold=True, color="red"),
            bs.Span(" → ", bold=True, color="muted"),
            *d.rich(after, bold=True),
        ]
        yy += _stat(d, rx, yy, rw, big, what, 34) + 20
    big = d.rich("{rqOneHOnePositive} of {rqOneHOneN}", bold=True)
    yy += _stat(d, rx, yy, rw, big, "patients lower, p = {rqOneHOneP}", 34) + 20
    d.band(
        (rx, yy, rw, cy + ch - yy),
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
    widths = [460.0, 198.0, CW - 460 - 198]
    cols = [CL, CL + widths[0], CL + widths[0] + widths[1]]
    heads = ["Study and data", "With the leak", "Leakage-free"]
    rh = 44.0
    y = CT - 2
    d.box(CL, y, CW, rh, fill="navy", line=None, radius=6)
    d.box(CL, y + rh - 8, CW, 8, fill="navy", line=None, radius=0)
    for c, wdt, head in zip(cols, widths, heads, strict=True):
        d.text((c + 18, y + 11, wdt - 24, 24), head, size=SMALL_PT, bold=True, color="white")
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
        d.text((cols[0] + 18, y + 11, widths[0] - 24, 26), label, size=BODY_PT)
        d.text((cols[1] + 18, y + 11, widths[1] - 24, 26), leaky, size=BODY_PT, color="red")
        if clean == "not reported":
            d.text((cols[2] + 18, y + 11, widths[2] - 24, 26), clean, size=BODY_PT, color="muted")
        else:
            d.text(
                (cols[2] + 18, y + 11, widths[2] - 24, 26),
                clean,
                size=BODY_PT,
                bold=True,
                color="blue",
            )
        y += rh
    d.line(CL, y, CR, y, color="navy", lw=1.25)
    d.text(
        (CL, y + 8, CW, 22),
        "Hand vs sixth finger for the stroke rows; left vs right hand for the healthy ones.",
        size=CAPTION_PT,
        color="muted",
    )
    by = y + 42
    d.band(
        (CL, by, CW, CB - by),
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
        size=SMALL_PT + 1,
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
    _, (cx, cy, cw, ch) = d.framed("setup", (CL, CT - 4, 590, 334), pad=6)
    rx = cx + cw + 28
    rw = CR - rx
    yy = cy + 2
    yy += (
        _stat(
            d,
            rx,
            yy,
            rw,
            d.rich("{rqTwoRestAhSfRctTslrKOneMean}%", bold=True),
            "with other patients, after {rqTwoMinutesKOne:sec} s",
            STAT_PT,
        )
        + 16
    )
    yy += (
        _stat(
            d,
            rx,
            yy,
            rw,
            d.rich("{rqTwoRestAhSfTsLrKOneMean}%", bold=True),
            "from scratch, same practice",
            STAT_PT,
            color="muted",
        )
        + 12
    )
    d.text((rx, yy, rw, 22), "Guessing: one in three", size=17, color="muted")
    yy += 36
    d.line(rx, yy - 6, CR, yy - 6, color="line", lw=0.75)
    d.text(
        (rx, yy + 6, rw, CB - yy - 6),
        [
            d.rich("Another day (exploratory)", bold=True, color="navy"),
            "unchanged {rqFourLaterPostUnchangedMean}%; five new trials of each movement, "
            "{rqFourLaterPostRecentredKFiveMean}%.",
        ],
        size=17,
        nums="blue",
        gap=2,
    )
    d.text(
        (CL, cy + ch + 10, cw, CB - cy - ch - 10),
        "**One transfer configuration** (H2a, p = {rqTwoHTwoAP}). With all "
        "{rqTwoMinutesKAll} min, from scratch ends {rqTwoRestAhSfTsLrMinusRctTslrKAllDiff} "
        "points higher: **not tested**.",
        size=17,
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
    _, (cx, cy, cw, ch) = d.framed("switch-patients", (CL, CT - 4, 578, 330), pad=6)
    rx = cx + cw + 28
    rw = CR - rx
    d.box(rx, cy + 2, 120, 26, fill="cream", line="gold", lw=1, radius=13)
    d.text(
        (rx, cy + 5, 120, 20), "Exploratory", size=CAPTION_PT, bold=True, color="navy", align="c"
    )
    yy = cy + 42
    yy += (
        _stat(
            d,
            rx,
            yy,
            rw,
            d.rich("{exFourTsLrCentralFiresAhMean}%", bold=True),
            "of hand windows fire it too",
            34,
            color="red",
        )
        + 14
    )
    half = (rw - 12) / 2
    a = _stat(
        d,
        rx,
        yy,
        half,
        d.rich("{exFiveFingerFingerOnMean}%", bold=True),
        "of periods caught, continuous",
        30,
    )
    b = _stat(
        d,
        rx + half + 12,
        yy,
        half,
        d.rich("{exFiveFingerFalsePerMinMean}", bold=True),
        "false a minute",
        30,
    )
    yy += max(a, b) + 12
    d.text((rx, yy, rw, 22), "No finger driven", size=17, color="muted")
    yy += 34
    d.band(
        (rx, yy, rw, CB - yy),
        "**No distinct sixth-finger command** (H3, H3c inconclusive): a move-or-rest switch.",
        size=17,
    )
    d.text(
        (CL, cy + ch + 10, cw, CB - cy - ch - 10),
        "Visual cues: finger vs rest best centrally ({rqFourCueSfRestCentralMean} vs "
        "{rqFourCueSfRestParietoOccipitalMean}%); hand vs finger best occipitally "
        "({rqFourCueAhSfParietoOccipitalMean} vs {rqFourCueAhSfCentralMean}%).",
        size=CAPTION_PT,
        color="muted",
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
    top, bh = CT, 200.0
    d.box(CL, top, CW, bh)
    d.box(CL, top, 6, bh, fill="blue", line=None, radius=0)
    d.text(
        (CL + 32, top + 18, CW - 60, bh - 36),
        "Leakage-free, hand against sixth finger scores {rqOneCspLdaReplicaCvLeakfreeMean}–"
        "{rqOneCspLdaCvLeakfreeMean}%, not the published {rqOnePublishedGroupBCspLda:int}%; "
        "one transfer configuration lifts a new patient from {rqTwoRestAhSfTsLrKOneMean}% to "
        "{rqTwoRestAhSfRctTslrKOneMean}% after one trial of each movement, then stays flat; and "
        "the sixth finger is, so far, a **move-or-rest switch**, not a command of its own.",
        size=LEAD_PT + 1,
        anchor="m",
        nums="blue",
    )
    fy = top + bh + 30
    d.text((CL, fy, CW, 30), "Future work", size=LEAD_PT, bold=True, color="navy")
    future = [
        ("Closed loop", "the switch drives a real finger, with patients"),
        ("Transfer that keeps learning", "e.g. a weight that grows with practice"),
    ]
    gap = 24.0
    fw = (CW - gap) / 2
    cy = fy + 42
    for i, (head, what) in enumerate(future):
        x = CL + i * (fw + gap)
        d.box(x, cy, fw, CB - cy)
        d.badge(x + 34, cy + 34, str(i + 1), r=14, fill="blue")
        d.text(
            (x + 64, cy + 20, fw - 84, CB - cy - 30),
            [d.rich(head, bold=True, color="navy"), d.rich(what)],
            size=BODY_PT,
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
    lw = 540.0
    d.box(CL, CT + 4, lw, 64, fill="navy", line=None, radius=10)
    d.text((CL + 24, CT + 20, lw - 48, 34), SITE + "/live", size=28, bold=True, color="white")
    d.bullets(
        (CL, CT + 100, lw, 220),
        [
            "Patient **{demoSubject}**, runs the model never saw",
            "Left: the cue. Middle: the EEG. Right: the model's reading",
            "Real held-out predictions, at real speed",
        ],
        size=LEAD_PT,
        gap=18,
    )
    d.framed("hand-finger", (CR - 288, CT, 288, 322), pad=20, align="r", valign="t")
    d.line(CL, 440, CR, 440, color="line", lw=0.75)
    d.text(
        (CL, 452, CW, 30),
        f"If it does not load: {SITE_COPY}/live, or the recorded video",
        size=SMALL_PT - 1,
        color="muted",
    )


def _closing_title(d: Deck, y: float) -> None:
    t = d.rec.slide.shapes.title
    _place(t, (PANEL_X, y, CR - PANEL_X, 64))
    _refill(d, t, [[bs.Span(d.rec.title, bold=True, size=48, color="navy")]])


def questions_slide(d: Deck) -> None:
    d.keep(
        8,
        0,
        "Thank you; we are happy to take questions. Likely ones: why the published score "
        "differs (the leak, slide on results), why so few minutes of practice (transfer), and "
        "what the finger is today (a candidate move-or-rest switch, tested offline only).",
        part="questions",
    )
    d.panel()
    _closing_title(d, 238)


def thanks_slide(d: Deck) -> None:
    rec = d.keep(
        9,
        10,
        f"Thank you. The page with the live demo and every result in this talk is at {SITE}.",
    )
    d.panel()
    _closing_title(d, 186)
    d.box(PANEL_X, 268, 56, 4, fill="gold", line=None, radius=0)
    d.text((PANEL_X, 292, CR - PANEL_X, 36), SITE, size=28, bold=True, color="blue")
    d.text(
        (PANEL_X, 344, CR - PANEL_X, 26),
        "        ".join(n for n, _ in STUDENTS),
        size=SMALL_PT,
        color="ink",
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

FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
PROBE = "Sfbprobe"


def package(raw: bytes, probe: bool = False) -> bytes:
    """The saved deck with the fonts embedded as PowerPoint embeds them, and fixed dates.

    With probe, every typeface and embedded font is renamed to a family no computer has, so a
    renderer can only draw the text from the fonts inside the file.
    """

    def face(name: str) -> str:
        return name.replace("Inter", PROBE) if probe else name

    panose = panose_of(FONT_FILES["regular"])
    fonts: list[tuple[str, str, str, bytes]] = []
    for i, (typeface, slot, kind) in enumerate(EMBED, start=1):
        ttf = (FONTS / FONT_FILES[kind]).read_bytes()
        if probe:
            ttf = renamed_font(ttf, "Inter", PROBE)
        fonts.append((f"rIdFont{i}", typeface, slot, eot(ttf)))
    families: dict[str, list[tuple[str, str]]] = {}
    for rid, typeface, slot, _ in fonts:
        families.setdefault(typeface, []).append((slot, rid))
    lst = "".join(
        f'<p:embeddedFont><p:font typeface="{face(t)}" panose="{panose}" pitchFamily="34" '
        f'charset="0"/>'
        + "".join(f'<p:{slot} r:id="{rid}"/>' for slot, rid in slots)
        + "</p:embeddedFont>"
        for t, slots in families.items()
    )

    def retype_xml(xml: str) -> str:
        # A face PowerPoint can match to a close one if the embedded font ever fails to load.
        for name in (FACE_SEMI, FACE):
            xml = re.sub(
                rf'<a:(latin|buFont) typeface="{name}"(?: panose="[^"]*")?\s*/>',
                rf'<a:\1 typeface="{face(name)}" panose="{panose}" pitchFamily="34" charset="0"/>',
                xml,
            )
        if probe:
            xml = xml.replace('typeface="Inter', f'typeface="{PROBE}')
        return xml

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            name = item.filename
            if name == "[Content_Types].xml":
                data = data.replace(
                    b'<Default Extension="xml"',
                    b'<Default Extension="fntdata" ContentType="application/x-fontdata"/>'
                    b'<Default Extension="xml"',
                )
            elif name == "ppt/_rels/presentation.xml.rels":
                rels = "".join(
                    f'<Relationship Id="{rid}" Type="{FONT_REL}" Target="fonts/font{i}.fntdata"/>'
                    for i, (rid, _, _, _) in enumerate(fonts, start=1)
                )
                data = data.replace(b"</Relationships>", rels.encode() + b"</Relationships>")
            elif name == "ppt/presentation.xml":
                xml = data.decode("utf-8")
                xml = xml.replace("<p:presentation ", '<p:presentation embedTrueTypeFonts="1" ', 1)
                xml, n = re.subn(
                    r"(<p:notesSz[^>]*/>(?:<p:smartTags[^>]*/>)?)",
                    rf"\g<1><p:embeddedFontLst>{lst}</p:embeddedFontLst>",
                    xml,
                    count=1,
                )
                if n != 1:
                    raise ValueError("presentation.xml has no notesSz to put the fonts after")
                data = xml.encode("utf-8")
            elif name.endswith(".xml") and name.startswith(("ppt/slide", "ppt/theme", "ppt/notes")):
                data = retype_xml(data.decode("utf-8")).encode("utf-8")
            elif name == "docProps/app.xml":
                data = app_xml(zin)
            info = zipfile.ZipInfo(name, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, data)
        for i, (_, _, _, blob) in enumerate(fonts, start=1):
            info = zipfile.ZipInfo(f"ppt/fonts/font{i}.fntdata", date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, blob)
    return out.getvalue()


def app_xml(zin: zipfile.ZipFile) -> bytes:
    n_slides = sum(1 for n in zin.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
        'docPropsVTypes"><Template>Wisp</Template><TotalTime>0</TotalTime>'
        "<Application>Microsoft Office PowerPoint</Application>"
        f"<PresentationFormat>Widescreen</PresentationFormat><Slides>{n_slides}</Slides>"
        f"<Notes>{n_slides}</Notes><HiddenSlides>0</HiddenSlides><Company></Company>"
        "<AppVersion>16.0000</AppVersion></Properties>"
    ).encode()


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
    return raw.getvalue()


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


def to_pdf(pptx: Path, outdir: Path) -> Path:
    """A PDF through LibreOffice with a fresh profile: no fonts but the system's and the deck's."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                str(SOFFICE),
                f"-env:UserInstallation=file://{Path(tmp) / 'profile'}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(pptx),
            ],
            check=True,
            timeout=600,
            capture_output=True,
        )
    return outdir / (pptx.stem + ".pdf")


def pdf_fonts(pdf: Path, family: str) -> list[str]:
    """Every font in the PDF must be embedded and be one of the family's weights."""
    out = subprocess.run(["pdffonts", str(pdf)], check=True, capture_output=True, text=True)
    problems = []
    names = set()
    for line in out.stdout.splitlines()[2:]:
        name = line.split()[0].split("+")[-1]
        names.add(name)
        flags = re.search(r"\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", line)
        if not re.fullmatch(rf"{family}-(Regular|SemiBold|Bold)", name):
            problems.append(f"{pdf.name}: font {name} is not one of the deck's")
        if not flags or flags.group(1) != "yes":
            problems.append(f"{pdf.name}: font {name} is not embedded")
    if not names:
        problems.append(f"{pdf.name}: no fonts found")
    return problems


def check_embedding(probe: bytes) -> list[str]:
    """The deck renamed to a family no computer has must still draw in it: LibreOffice then
    took every run's font from the fonts embedded in the file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.pptx"
        path.write_bytes(probe)
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            names = z.namelist()
            ct = z.read("[Content_Types].xml").decode()
            rels = z.read("ppt/_rels/presentation.xml.rels").decode()
        problems = [f"probe: {bad} is damaged"] if bad else []
        fonts = [n for n in names if n.startswith("ppt/fonts/")]
        if len(fonts) != len(EMBED) or 'Extension="fntdata"' not in ct:
            problems.append("probe: the font parts or their content type are missing")
        if rels.count(FONT_REL) != len(EMBED):
            problems.append("probe: the font relationships are missing")
        problems += pdf_fonts(to_pdf(path, Path(tmp)), PROBE)
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
        if rec.chrome:
            d.number_slide(rec)
    d.notes()

    problems = d.check_text() + d.check_shapes() + d.check_figures()
    talk = sum(r.seconds for r in d.records if r.part == "talk")
    if talk != TALK_SECONDS:
        problems.append(f"the talk comes to {talk} s, not {TALK_SECONDS}")
    raw = finish(d.prs)
    blob = package(raw)
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
        bad = check_embedding(package(raw, probe=True))
        if bad:
            print("\n".join(bad), file=sys.stderr)
            return 1
        print("embedded fonts: every run draws from the fonts inside the .pptx")
        pdf = to_pdf(OUT, OUT.parent)
        bad = pdf_fonts(pdf, "Inter")
        if bad:
            print("\n".join(bad), file=sys.stderr)
            return 1
        print(f"wrote {pdf.relative_to(ROOT)}, fonts embedded: Inter Regular, SemiBold, Bold")
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
