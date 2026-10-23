"""Draw every slide of the deck as a 1366 x 768 picture, the projector's size, to look at.

uv run --with python-pptx==1.0.2 python report/slides/preview_slides.py

For machines without LibreOffice: the .pptx is read back with python-pptx and each slide is
laid out again in HTML, shape by shape, in Inter (the page's own font file), then photographed
by the page's Playwright Chromium. Text that runs past its box is listed. The pictures go to
report/slides/previews/ (not committed), with contact.png showing all slides at once.
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image
from pptx import Presentation
from pptx.enum.dml import MSO_FILL
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DECK = HERE / "sixth-finger-bci.pptx"
OUT = HERE / "previews"
FONT = (
    ROOT
    / "web"
    / "node_modules"
    / "@fontsource-variable"
    / "inter"
    / "files"
    / "inter-latin-wght-normal.woff2"
)
PLAYWRIGHT = ROOT / "web" / "node_modules" / "playwright"
PX_W, PX_H = 1366, 768
LINE = (1984 + 494) / 2048
DASHES = {
    "dash": (4, 3),
    "sysDash": (3, 1),
    "sysDot": (1, 1),
    "roundDot": (0.01, 2),
    "lgDash": (8, 3),
}


class Frame:
    """Maps slide EMU into picture pixels, through any group transforms on the way down."""

    def __init__(
        self, k: float, ox: float = 0, oy: float = 0, sx: float = 1, sy: float = 1
    ) -> None:
        self.k, self.ox, self.oy, self.sx, self.sy = k, ox, oy, sx, sy

    def x(self, v: float) -> float:
        return (self.ox + v * self.sx) * self.k

    def y(self, v: float) -> float:
        return (self.oy + v * self.sy) * self.k

    def into(self, group: Any) -> Frame:
        xfrm = group._element.grpSpPr.find(qn("a:xfrm"))
        off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
        choff, chext = xfrm.find(qn("a:chOff")), xfrm.find(qn("a:chExt"))
        sx = int(ext.get("cx")) / max(1, int(chext.get("cx")))
        sy = int(ext.get("cy")) / max(1, int(chext.get("cy")))
        ox = int(off.get("x")) - int(choff.get("x")) * sx
        oy = int(off.get("y")) - int(choff.get("y")) * sy
        return Frame(
            self.k, self.ox + ox * self.sx, self.oy + oy * self.sy, self.sx * sx, self.sy * sy
        )


def colour(fill: Any) -> str | None:
    try:
        if fill.type == MSO_FILL.SOLID:
            return f"#{fill.fore_color.rgb}"
    except (AttributeError, TypeError):
        return None
    return None


def stroke(shape: Any, k: float) -> tuple[str | None, float, str]:
    ln = shape._element.spPr.find(qn("a:ln"))
    if ln is None or ln.find(qn("a:noFill")) is not None:
        return None, 0, ""
    clr = ln.find(f"{qn('a:solidFill')}/{qn('a:srgbClr')}")
    width = int(ln.get("w", "12700")) * k
    dash = ln.find(qn("a:prstDash"))
    pattern = ""
    if dash is not None and dash.get("val") in DASHES:
        a, b = DASHES[dash.get("val")]
        pattern = f"stroke-dasharray:{a * width:.2f} {b * width:.2f};"
        if dash.get("val") == "roundDot":
            pattern += "stroke-linecap:round;"
    return (f"#{clr.get('val')}" if clr is not None else "#000"), width, pattern


def text_html(shape: Any, f: Frame, left: float, top: float, w: float, h: float) -> str:
    tf = shape.text_frame
    body = tf._txBody.find(qn("a:bodyPr"))
    anchor = {"t": "flex-start", "ctr": "center", "b": "flex-end"}.get(
        body.get("anchor", "t"), "flex-start"
    )
    paras = []
    for p in tf.paragraphs:
        runs, sizes = [], []
        for el in p._p:
            if el.tag not in (qn("a:r"), qn("a:fld")):
                continue
            rpr = el.find(qn("a:rPr"))
            text = el.find(qn("a:t")).text or ""
            size = int(rpr.get("sz", "1800")) / 100 if rpr is not None else 18
            sizes.append(size)
            latin = rpr.find(qn("a:latin")) if rpr is not None else None
            clr = rpr.find(f"{qn('a:solidFill')}/{qn('a:srgbClr')}") if rpr is not None else None
            style = [
                f"font-size:{size * f.k * 12700:.2f}px",
                f"font-family:'{latin.get('typeface') if latin is not None else 'Inter'}'",
                f"font-weight:{700 if rpr is not None and rpr.get('b') == '1' else 400}",
                f"color:#{clr.get('val') if clr is not None else '000'}",
            ]
            if rpr is not None and rpr.get("i") == "1":
                style.append("font-style:italic")
            if rpr is not None and rpr.get("spc"):
                style.append(f"letter-spacing:{int(rpr.get('spc')) / 100 * f.k * 12700:.2f}px")
            if rpr is not None and rpr.get("baseline"):
                style.append("vertical-align:super;font-size:60%")
            runs.append(f'<span style="{";".join(style)}">{html.escape(text)}</span>')
        size = max(sizes) if sizes else 18
        spacing = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
        before = (p.space_before.pt if p.space_before is not None else 0) * f.k * 12700
        align = {1: "left", 2: "center", 3: "right"}.get(int(p.alignment or 1), "left")
        px = size * f.k * 12700
        style = (
            f"margin:{before:.2f}px 0 0;text-align:{align};font-size:{px:.2f}px;"
            f"line-height:{px * LINE * spacing:.2f}px"
        )
        paras.append(f'<p style="{style}">{"".join(runs) or "&nbsp;"}</p>')
    return (
        f'<div class="t" style="left:{left:.2f}px;top:{top:.2f}px;width:{w:.2f}px;height:{h:.2f}px;'
        f'justify-content:{anchor}">{"".join(paras)}</div>'
    )


def shape_html(shape: Any, f: Frame) -> str:
    st = shape.shape_type
    if st == MSO_SHAPE_TYPE.GROUP:
        inner = f.into(shape)
        return "".join(shape_html(s, inner) for s in shape.shapes)
    left, top = f.x(shape.left), f.y(shape.top)
    w, h = shape.width * f.sx * f.k, shape.height * f.sy * f.k
    out = []
    if st == MSO_SHAPE_TYPE.PICTURE:
        data = base64.b64encode(shape.image.blob).decode()
        out.append(
            f'<img src="data:{shape.image.content_type};base64,{data}" '
            f'style="left:{left:.2f}px;top:{top:.2f}px;width:{w:.2f}px;height:{h:.2f}px">'
        )
    elif shape._element.tag == qn("p:cxnSp"):
        x1, y1 = f.x(shape.begin_x), f.y(shape.begin_y)
        x2, y2 = f.x(shape.end_x), f.y(shape.end_y)
        clr, width, dash = stroke(shape, f.k * f.sx)
        out.append(
            f'<svg><line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'style="stroke:{clr};stroke-width:{width:.2f}px;{dash}"/></svg>'
        )
    elif st in (
        MSO_SHAPE_TYPE.AUTO_SHAPE,
        MSO_SHAPE_TYPE.FREEFORM,
        MSO_SHAPE_TYPE.TEXT_BOX,
        MSO_SHAPE_TYPE.PLACEHOLDER,
    ):
        fill = colour(shape.fill) if st != MSO_SHAPE_TYPE.PLACEHOLDER else None
        clr, width, dash = (
            stroke(shape, f.k * f.sx) if st != MSO_SHAPE_TYPE.PLACEHOLDER else (None, 0, "")
        )
        paint = f"fill:{fill or 'none'};stroke:{clr or 'none'};stroke-width:{width:.2f}px;{dash}"
        geom = shape._element.spPr.find(qn("a:custGeom"))
        prst = shape._element.spPr.find(qn("a:prstGeom"))
        kind = prst.get("prst") if prst is not None else None
        if geom is not None:
            for path in geom.iter(qn("a:path")):
                pw, ph = int(path.get("w")), int(path.get("h"))
                d = []
                for el in path:
                    if el.tag == qn("a:close"):
                        d.append("Z")
                        continue
                    pt = el.find(qn("a:pt"))
                    px = left + int(pt.get("x")) / max(1, pw) * w
                    py = top + int(pt.get("y")) / max(1, ph) * h
                    d.append(f"{'M' if el.tag == qn('a:moveTo') else 'L'}{px:.2f},{py:.2f}")
                out.append(
                    f'<svg><path d="{" ".join(d)}" style="{paint};stroke-linejoin:round"/></svg>'
                )
        elif kind == "ellipse" and (fill or clr):
            out.append(
                f'<svg><ellipse cx="{left + w / 2:.2f}" cy="{top + h / 2:.2f}" rx="{w / 2:.2f}" '
                f'ry="{h / 2:.2f}" style="{paint}"/></svg>'
            )
        elif kind in ("rect", "roundRect") and (fill or clr):
            r = 0.0
            if kind == "roundRect":
                gd = prst.find(f"{qn('a:avLst')}/{qn('a:gd')}")
                adj = int(gd.get("fmla").split()[1]) / 100000 if gd is not None else 0.16667
                r = adj * min(w, h)
            out.append(
                f'<svg><rect x="{left:.2f}" y="{top:.2f}" width="{w:.2f}" height="{h:.2f}" '
                f'rx="{r:.2f}" style="{paint}"/></svg>'
            )
        if shape.has_text_frame:
            body = shape.text_frame._txBody
            if shape.text_frame.text.strip() or body.find(f".//{qn('a:fld')}") is not None:
                out.append(text_html(shape, f, left, top, w, h))
    return "".join(out)


def page(prs: Presentation) -> str:
    k = PX_W / prs.slide_width
    f = Frame(k)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        bg = colour(slide.background.fill) or "#fff"
        body = "".join(shape_html(s, f) for s in slide.shapes)
        slides.append(f'<section id="s{i}" style="background:{bg}">{body}</section>')
    font = FONT.as_uri()
    return f"""<!doctype html><meta charset="utf-8"><style>
@font-face{{font-family:Inter;src:url("{font}") format("woff2");font-weight:100 900}}
body{{margin:0;background:#888}}
section{{position:relative;width:{PX_W}px;height:{PX_H}px;overflow:hidden;margin:0 0 8px}}
section>*{{position:absolute}}
svg{{position:absolute;left:0;top:0;width:{PX_W}px;height:{PX_H}px;overflow:visible}}
.t{{display:flex;flex-direction:column;overflow:visible;font-family:Inter;
  -webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01"}}
.t p{{white-space:pre-wrap;overflow-wrap:normal}}
</style>{"".join(slides)}"""


SHOOT = """
const { chromium } = require(process.argv[1]);
const [file, out] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await page.goto("file://" + file);
  await page.evaluate(() => document.fonts.ready);
  const over = await page.evaluate(() =>
    [...document.querySelectorAll("section")].flatMap((s, i) =>
      [...s.querySelectorAll(".t")]
        .filter((t) => t.scrollHeight > t.clientHeight + 2 || t.scrollWidth > t.clientWidth + 2)
        .map((t) => `slide ${i + 1}: "${t.innerText.slice(0, 50)}" runs past its box`)));
  const sections = await page.$$("section");
  for (let i = 0; i < sections.length; i++) {
    await sections[i].screenshot({ path: `${out}/slide-${String(i + 1).padStart(2, "0")}.png` });
  }
  console.log(JSON.stringify(over));
  await browser.close();
})();
"""


def contact(paths: list[Path]) -> None:
    cols, tw = 4, PX_W // 4
    th = PX_H // 4
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 8) + 8), (136, 136, 136))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 8)))
    sheet.save(OUT / "contact.png")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("slide-*.png"):
        old.unlink()
    doc = OUT / "slides.html"
    doc.write_text(page(Presentation(str(DECK))))
    res = subprocess.run(
        ["node", "-e", SHOOT, str(PLAYWRIGHT), str(doc), str(OUT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode:
        print(res.stderr, file=sys.stderr)
        return 1
    over = json.loads(res.stdout.strip().splitlines()[-1])
    shots = sorted(OUT.glob("slide-*.png"))
    contact(shots)
    print(f"{len(shots)} slides drawn in {OUT.relative_to(ROOT)}")
    for line in over:
        print(line)
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
