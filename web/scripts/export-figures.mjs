// Cuts the page's figures out one at a time for the paper, the report and the slides. Each one
// is taken from the built page as it stands, alone, at a fixed width and at rest (no demo, no
// pointer, no animation), and written to docs/figures/web/ as a vector PDF sized to it, a PNG at
// 3x and, where the figure is a single SVG, that SVG with its computed styles written in. The
// paper's figures are copied on to paper/figures/web/.
//
//   npm run figures                    build the site, then every figure
//   npm run figures -- leak setup      only these
//   npm run figures -- --no-build      reuse the last build
//
// It also checks the smallest text of each figure where it will be printed: at least 7 pt at the
// paper's column (3.5 in) or full width (7.16 in), at least 8 pt across the report's text width
// (5.77 in, 12 pt body) for the report's own cuts, and at least 24 px on a 1920 px slide.

import { spawnSync } from "node:child_process";
import { copyFileSync, createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, extname, join, normalize, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(WEB, "..");
const OUT = join(ROOT, "docs", "figures", "web");
const PAPER_OUT = join(ROOT, "paper", "figures", "web");
const SITE = join(tmpdir(), "sixth-finger-figures-site");
const FONTS = join(tmpdir(), "sixth-finger-figures-fonts");
const FONT = join(WEB, "node_modules", "@fontsource-variable", "inter", "files", "inter-latin-wght-normal.woff2");

// Every weight the page's type uses, each set from its own static font (see staticInter).
const WEIGHTS = [400, 450, 500, 520, 560, 600, 700];
const PRINT_FONTS = WEIGHTS.map(
  (w) => `@font-face{font-family:"Inter Print";font-weight:${w};src:url(/figure-fonts/inter-${w}.ttf)}`,
).join("\n");
const DOC_CSS = [
  PRINT_FONTS,
  'html.doc{--sans:"Inter Print",system-ui,sans-serif}',
  readFileSync(join(WEB, "scripts", "export-figures.css"), "utf8"),
].join("\n");

const SCALE = 3;
const MIN_PT = 7;
// The report is set in 12 pt, so its figures keep their text at 8 pt or more.
const MIN_REPORT_PT = 8;
const MIN_SLIDE_PX = 24;
// IEEE two-column: one column and the full text width, in points.
const PAPER_PT = { column: 3.5 * 72, full: 7.16 * 72, report: 5.77 * 72 };
// The box a figure may fill on a 1920 x 1080 slide under its title, alone or beside text.
const SLIDE_BOX = { full: [1760, 860], half: [860, 860] };

// The page's desktop layout, whatever the figure's width; "phone" lays the page out at the
// figure's own width, for the figures whose narrow layout reads better in a column.
const DESKTOP = 1280;

// The figures the paper is likely to use; the report reads all of them from docs/figures/.
const IN_PAPER = [
  "system",
  "trial",
  "model",
  "leak",
  "leak-slope",
  "elsewhere",
  "switch-patients",
  "switch-on",
  "setup",
  "session",
  "later",
  "later-adjusted",
  "path",
];

/**
 * Every figure: where it is on the page, the width it is laid out at (CSS px), where it goes in
 * the paper and on a slide, what to set before it is cut out, and which of its parts, if any,
 * is a pure SVG.
 */
const FIGURES = [
  { name: "system", find: "#what figure.plate-chain", width: 760, paper: "full", slide: "full" },
  { name: "trial", find: "#data figure.plate-sees", width: 450, paper: "column", slide: "half" },
  { name: "session", find: "#data figure.plate-session", width: 760, paper: "full", slide: "full" },
  {
    name: "sensors",
    find: "#data figure.plate:has(.head-svg)",
    width: 560,
    paper: "column",
    slide: "half",
    svg: ".head-svg",
  },
  {
    name: "rhythm",
    find: "#what figure.plate:has(.rhythm-svg)",
    width: 760,
    paper: "column",
    slide: "full",
    svg: ".rhythm-svg",
    // The drop shows only while imagining; the resting size stays behind it in grey.
    before: (page) => page.locator("#what .rhythm-toggle [role=radio]").nth(1).click(),
  },
  {
    name: "rhythm-measured",
    find: "#command figure.plate:has(.chart)",
    width: 430,
    paper: "column",
    slide: "half",
    svg: ".chart svg",
  },
  { name: "model", find: "#demo figure.plate-mdraw", width: 760, paper: "full", slide: "full" },
  { name: "leak", find: "#published figure.leak", width: 440, layout: "phone", paper: "column", slide: "half" },
  {
    name: "leak-slope",
    find: "#published .chart:has(.chart-columns)",
    width: 430,
    paper: "column",
    slide: "half",
  },
  {
    name: "elsewhere",
    find: "#published figure.plate-elsewhere",
    width: 760,
    paper: "full",
    slide: "full",
  },
  {
    name: "switch-patients",
    find: "#command figure.figure",
    width: 430,
    paper: "column",
    slide: "half",
    svg: ".chart svg",
  },
  { name: "switch-on", find: "#command .hbars", width: 440, paper: "column", slide: "half" },
  {
    name: "switch-on-sure",
    find: "#command .hbars",
    width: 440,
    paper: "column",
    slide: "half",
    before: (page) => page.locator("#command .follow:has(.hbars) .toggle [role=radio]").nth(1).click(),
  },
  {
    name: "switch-sure",
    find: "#command .chart:has(.chart-rule)",
    width: 430,
    paper: "column",
    slide: "half",
    svg: "svg",
  },
  { name: "path", find: "#use figure.journey", width: 1000, paper: "full", slide: "full" },
  { name: "path-lanes", find: "#use figure.journey", width: 500, paper: "column", slide: "half" },
  {
    name: "setup",
    find: "#use .chart:has(.chart-series)",
    width: 430,
    paper: "column",
    slide: "half",
    svg: "svg",
  },
  { name: "later", find: "#use .hbars", width: 440, paper: "column", slide: "half" },
  {
    name: "later-adjusted",
    find: "#use .hbars",
    width: 440,
    paper: "column",
    slide: "half",
    before: (page) => page.locator("#use .follow:has(.hbars) .toggle [role=radio]").nth(1).click(),
  },
  // The report's text width is narrower than the paper's two columns, so its wide figures are
  // laid out narrower: the drawings shrink to fit and the words keep their size.
  { name: "system-report", find: "#what figure.plate-chain", width: 560, paper: "report" },
  { name: "session-report", find: "#data figure.plate-session", width: 600, paper: "report" },
  { name: "model-report", find: "#demo figure.plate-mdraw", width: 540, paper: "report" },
  { name: "elsewhere-report", find: "#published figure.plate-elsewhere", width: 560, paper: "report" },
  { name: "path-report", find: "#use figure.journey", width: 760, paper: "report" },
  ...["published", "command", "use"].map((q) => ({
    name: `dial-${q}`,
    find: `#${q} .q-dial`,
    width: 240,
    slide: "half",
    svg: ".gauge",
  })),
];

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
};

/** When the page last changed, as a PDF date, so exporting an unchanged page writes the same bytes. */
function pageDate() {
  const res = spawnSync("git", ["log", "-1", "--format=%cd", "--date=format-local:%Y%m%d%H%M%S", "--", "web"], {
    cwd: ROOT,
    env: { ...process.env, TZ: "UTC" },
  });
  const date = res.stdout?.toString().trim();
  return /^\d{14}$/.test(date) ? date : null;
}

/**
 * Inter at each weight as a plain TrueType font. Chromium writes a variable font into a PDF as
 * Type 3 glyphs, which IEEE's PDF checks refuse (the reason plots.py sets pdf.fonttype 42), so
 * the figures are set in static instances of the same font, cut from the page's own file.
 */
function staticInter() {
  if (WEIGHTS.every((w) => existsSync(join(FONTS, `inter-${w}.ttf`)))) return;
  console.log("cutting static Inter instances");
  mkdirSync(FONTS, { recursive: true });
  const py = [
    "import sys",
    "from fontTools.ttLib import TTFont",
    "from fontTools.varLib.instancer import instantiateVariableFont",
    "src, out, *weights = sys.argv[1:]",
    "for w in weights:",
    "    font = instantiateVariableFont(TTFont(src), {'wght': int(w)})",
    "    font.flavor = None",
    "    for rec in font['name'].names:",
    "        if rec.nameID in (4, 6):",
    "            rec.string = f'Inter-{w}'",
    "    font.save(f'{out}/inter-{w}.ttf')",
  ].join("\n");
  // fontTools comes from the project's lock; brotli only to read the woff2.
  const args = ["run", "--with", "brotli==1.2.1", "python", "-c", py, FONT, FONTS, ...WEIGHTS.map(String)];
  const res = spawnSync("uv", args, { cwd: ROOT, stdio: "inherit" });
  if (res.status !== 0) throw new Error("could not cut the static fonts (needs uv)");
}

function build() {
  console.log("building the site");
  const vite = join(WEB, "node_modules", "vite", "bin", "vite.js");
  const args = [vite, "build", "--outDir", SITE, "--emptyOutDir", "--logLevel", "warn"];
  const res = spawnSync(process.execPath, args, { cwd: WEB, stdio: "inherit" });
  if (res.status !== 0) throw new Error("vite build failed");
}

/** Serves the build on a free port; the figures need no API, and the demo is kept off. */
function serve() {
  const server = createServer((req, res) => {
    const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
    const fonts = path.startsWith("/figure-fonts/");
    const dir = fonts ? FONTS : SITE;
    let file = join(dir, fonts ? path.slice("/figure-fonts/".length) : path);
    if (!file.startsWith(dir) || !existsSync(file) || statSync(file).isDirectory()) {
      file = join(SITE, "index.html");
    }
    res.writeHead(200, { "Content-Type": MIME[extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// From here to svgOf, the functions run inside the page.

/** Leaves only the figure on the page, at its width, and fixes the layout the page has now. */
function isolate({ find, width, css }) {
  const el = document.querySelector(find);
  if (!el) throw new Error(`no element for ${find}`);
  const style = document.createElement("style");
  style.textContent = css;
  document.head.append(style);
  document.documentElement.classList.add("doc");
  el.setAttribute("data-fig", "");
  for (let a = el.parentElement; a; a = a.parentElement) a.setAttribute("data-fig-path", "");
  el.style.setProperty("--fig-w", `${width}px`);
  // Media queries are settled here, at the layout chosen, so neither the print layout nor
  // resizing the window to the figure brings in another one.
  const freeze = (rules) => {
    for (const rule of rules) {
      if (rule instanceof CSSMediaRule) {
        const on = window.matchMedia(rule.media.mediaText).matches;
        freeze(rule.cssRules);
        rule.media.mediaText = on ? "all" : "not all";
      } else if (rule.cssRules) freeze(rule.cssRules);
    }
  };
  for (const sheet of document.styleSheets) freeze(sheet.cssRules);
}

/** Whether an element paints anything: shown, not see-through, and for a shape, inked. */
function inked(el) {
  for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
    const s = getComputedStyle(a);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) return false;
  }
  if (el instanceof HTMLElement) {
    // Words kept for screen readers only, clipped to a pixel.
    const box = el.getBoundingClientRect();
    return !(box.width <= 1 && box.height <= 1 && getComputedStyle(el).overflow === "hidden");
  }
  if (!(el instanceof SVGGeometryElement)) return true;
  const s = getComputedStyle(el);
  const clear = (paint) => paint === "none" || /rgba\(.*,\s*0\)$/.test(paint) || paint === "transparent";
  return !(clear(s.fill) && clear(s.stroke));
}

/** The box around everything the root draws, on screen; blurred shadows count at full spread. */
function inkBox(root) {
  const box = { l: Infinity, t: Infinity, r: -Infinity, b: -Infinity };
  const add = (r, pad = 0) => {
    if (r.width === 0 && r.height === 0) return;
    box.l = Math.min(box.l, r.left - pad);
    box.t = Math.min(box.t, r.top - pad);
    box.r = Math.max(box.r, r.right + pad);
    box.b = Math.max(box.b, r.bottom + pad);
  };
  const all = [root, ...root.querySelectorAll("*")];
  for (const el of all) {
    if (!inked(el)) continue;
    const drawn = el instanceof SVGGeometryElement || el instanceof SVGTextContentElement;
    if (el instanceof SVGElement && !drawn) continue;
    if (el instanceof SVGElement) {
      const blur = /blur\(([\d.]+)px\)/.exec(getComputedStyle(el).filter);
      const width = parseFloat(getComputedStyle(el).strokeWidth) || 0;
      add(el.getBoundingClientRect(), blur ? 2 * Number(blur[1]) * (el.getScreenCTM()?.a ?? 1) : width);
    } else {
      const s = getComputedStyle(el);
      const bordered = ["Top", "Right", "Bottom", "Left"].some((side) => s[`border${side}Width`] !== "0px");
      const painted = s.backgroundColor !== "rgba(0, 0, 0, 0)" || bordered || s.boxShadow !== "none";
      // A drawn ::before or ::after (a key's swatch) sits inside its element's box.
      const pseudo = ["::before", "::after"].some((p) => !["none", "normal"].includes(getComputedStyle(el, p).content));
      if (painted || pseudo || el instanceof HTMLImageElement) add(el.getBoundingClientRect());
      for (const node of el.childNodes) {
        if (node.nodeType !== 3 || !node.textContent.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const r of range.getClientRects()) add(r);
      }
    }
  }
  return { x: box.l, y: box.t, w: box.r - box.l, h: box.b - box.t };
}

/** Moves the figure so its ink starts `pad` from the page's corner, and gives the page's size. */
function frame({ pad }) {
  const el = document.querySelector("[data-fig]");
  const ink = inkBox(el);
  const own = el.getBoundingClientRect();
  el.style.setProperty("--fig-x", `${Math.round(own.left - ink.x + pad)}px`);
  el.style.setProperty("--fig-y", `${Math.round(own.top - ink.y + pad)}px`);
  return { w: Math.ceil(ink.w + 2 * pad), h: Math.ceil(ink.h + 2 * pad) };
}

/** The smallest text in the figure, in CSS px as drawn, and what it says. */
function smallestText() {
  const el = document.querySelector("[data-fig]");
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let min = { px: Infinity, text: "" };
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const host = node.parentElement;
    if (!node.textContent.trim() || !host || !inked(host)) continue;
    if (host instanceof SVGElement && !(host instanceof SVGTextContentElement)) continue;
    // Lettering drawn on a device (the model box's "EEGNet") is part of the drawing, not a label.
    if (host.closest(".iso-face-text")) continue;
    let px = parseFloat(getComputedStyle(host).fontSize);
    if (host instanceof SVGElement) {
      const m = host.getScreenCTM();
      if (m) px *= Math.hypot(m.a, m.b);
    }
    if (px < min.px) min = { px, text: node.textContent.trim().slice(0, 40) };
  }
  return min;
}

/** The figure's own SVG, its computed styles written in, framed to its ink. */
function svgOf({ part, fontUrl }) {
  const root = document.querySelector("[data-fig]");
  const svg = root.querySelector(part);
  if (!(svg instanceof SVGSVGElement)) throw new Error(`no svg for ${part}`);
  const INHERITED = [
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "paint-order",
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "letter-spacing",
    "text-anchor",
  ];
  const OWN = { opacity: "1", "vector-effect": "none", "dominant-baseline": "auto", "mix-blend-mode": "normal" };
  const plain = (v) => v.replace(/(-?[\d.]+)px/g, "$1").replace(/,\s+/g, ", ");
  const copy = svg.cloneNode(true);
  const filters = new Map();
  const walk = (src, dst, parent) => {
    const s = getComputedStyle(src);
    const mine = {};
    for (const p of INHERITED) {
      const v = s.getPropertyValue(p);
      mine[p] = v;
      // The print font is the page's own Inter, which the file carries as "Inter Variable".
      const out = p === "font-family" ? v.replace('"Inter Print"', '"Inter Variable", Inter') : plain(v);
      if (!parent || parent[p] !== v) dst.setAttribute(p, out);
    }
    for (const [p, initial] of Object.entries(OWN)) {
      const v = s.getPropertyValue(p);
      if (v && v !== initial) dst.setAttribute(p, plain(v));
    }
    if (s.transform !== "none" && src !== svg) {
      dst.setAttribute("transform", s.transform.replace(/,\s*/g, " "));
    }
    const blur = /blur\(([\d.]+)px\)/.exec(s.filter);
    if (blur) {
      const id = `blur-${blur[1].replace(".", "-")}`;
      filters.set(id, blur[1]);
      dst.setAttribute("filter", `url(#${id})`);
    } else dst.removeAttribute("filter");
    if (src instanceof SVGCircleElement) dst.setAttribute("r", plain(s.r));
    for (const a of [...dst.attributes]) {
      if (/^(class|style|tabindex|role|data-.*|aria-.*)$/.test(a.name)) dst.removeAttribute(a.name);
    }
    const kids = [...src.children];
    const copies = [...dst.children];
    kids.forEach((k, i) => {
      if (!inked(k) && !(k instanceof SVGDefsElement)) copies[i].remove();
      else walk(k, copies[i], mine);
    });
  };
  walk(svg, copy, null);
  copy.querySelectorAll("defs").forEach((d) => d.childElementCount === 0 && d.remove());
  copy.querySelectorAll("g").forEach((g) => g.childNodes.length === 0 && g.remove());

  // Frame to the same ink the PDF and PNG are framed to, in the drawing's own units.
  const ink = inkBox(svg);
  const m = svg.getScreenCTM().inverse();
  const at = (x, y) => new DOMPoint(x, y).matrixTransform(m);
  const a = at(ink.x, ink.y);
  const b = at(ink.x + ink.w, ink.y + ink.h);
  const pad = 4;
  const k = (b.x - a.x) / ink.w;
  const view = [a.x - pad * k, a.y - pad * k, b.x - a.x + 2 * pad * k, b.y - a.y + 2 * pad * k];
  copy.setAttribute("viewBox", view.map((v) => +v.toFixed(2)).join(" "));
  copy.setAttribute("width", String(Math.ceil(ink.w + 2 * pad)));
  copy.setAttribute("height", String(Math.ceil(ink.h + 2 * pad)));
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  for (const [id, sd] of filters) {
    const f = document.createElementNS("http://www.w3.org/2000/svg", "filter");
    f.setAttribute("id", id);
    for (const [name, v] of Object.entries({ x: "-50%", y: "-50%", width: "200%", height: "200%" })) {
      f.setAttribute(name, v);
    }
    const blur = document.createElementNS("http://www.w3.org/2000/svg", "feGaussianBlur");
    blur.setAttribute("stdDeviation", sd);
    f.append(blur);
    defs.append(f);
  }
  if (copy.querySelector("text")) {
    const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent =
      `@font-face{font-family:"Inter Variable";font-weight:100 900;src:url(${fontUrl}) format("woff2")}` +
      'text{font-feature-settings:"cv11","ss01";font-variant-numeric:tabular-nums}';
    defs.append(style);
  }
  if (defs.childElementCount) copy.prepend(defs);
  return new XMLSerializer().serializeToString(copy);
}

// They go in as one script so they can call each other.
const IN_PAGE = [isolate, inked, inkBox, frame, smallestText, svgOf].map(String).join("\n");
const call = (page, name, arg) => page.evaluate(([n, a]) => window[n](a), [name, arg]);

/** The fonts a PDF carries: how many are embedded as font files, and how many as Type 3. */
function pdfFonts(buf) {
  const text = buf.toString("latin1");
  return {
    embedded: (text.match(/\/FontFile[23]?\b/g) ?? []).length,
    type3: (text.match(/\/Subtype\s*\/Type3/g) ?? []).length,
  };
}

async function exportFigure(browser, base, fig, { fontUrl, date }) {
  const layout = fig.layout === "phone" ? fig.width : DESKTOP;
  const context = await browser.newContext({
    viewport: { width: layout, height: 1000 },
    deviceScaleFactor: SCALE,
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  // No demo: its live parts (the paper's ink, the lit lamp) stay at rest.
  await page.route("**/demo/**", (route) => route.abort());
  await page.goto(`${base}/?server=none`, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
  if (fig.before) await fig.before(page);
  await page.addScriptTag({ content: IN_PAGE });
  await call(page, "isolate", { find: fig.find, width: fig.width, css: DOC_CSS });
  await page.evaluate(`document.documentElement.dataset.figure = ${JSON.stringify(fig.name)}`);
  await page.evaluate(() => document.fonts.ready);
  // Charts measure their width in a ResizeObserver; give them a frame or two to redraw.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(150);
  const size = await call(page, "frame", { pad: 6 });
  await page.setViewportSize({ width: size.w, height: size.h });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const again = await call(page, "frame", { pad: 6 });
  if (again.w !== size.w || again.h !== size.h) throw new Error(`${fig.name}: layout moved when framed`);
  await page.addStyleTag({ content: `html,body{width:${size.w}px;height:${size.h}px;overflow:hidden}` });

  const files = [];
  const png = join(OUT, `${fig.name}.png`);
  await page.screenshot({ path: png, clip: { x: 0, y: 0, width: size.w, height: size.h } });
  files.push(png);
  await page.emulateMedia({ media: "screen" });
  let pdf = await page.pdf({
    width: `${size.w}px`,
    height: `${size.h}px`,
    printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });
  const pages = Number(/\/Count (\d+)/.exec(pdf.toString("latin1"))?.[1]);
  if (pages !== 1) throw new Error(`${fig.name}: the PDF has ${pages} pages`);
  // Same length, so the cross-reference offsets stay right.
  if (date) pdf = Buffer.from(pdf.toString("latin1").replace(/(Date \(D:)\d{14}/g, `$1${date}`), "latin1");
  writeFileSync(join(OUT, `${fig.name}.pdf`), pdf);
  files.push(join(OUT, `${fig.name}.pdf`));
  if (fig.svg) {
    const svg = await call(page, "svgOf", { part: fig.svg, fontUrl });
    writeFileSync(join(OUT, `${fig.name}.svg`), `${svg}\n`);
    files.push(join(OUT, `${fig.name}.svg`));
  }
  const text = await call(page, "smallestText");
  await context.close();
  return { size, text, fonts: pdfFonts(pdf), files };
}

function legibility(fig, { size, text }) {
  const notes = [];
  let ok = true;
  if (fig.paper && Number.isFinite(text.px)) {
    const pt = (text.px * PAPER_PT[fig.paper]) / size.w;
    const report = fig.paper === "report";
    if (pt < (report ? MIN_REPORT_PT : MIN_PT)) ok = false;
    notes.push(`${pt.toFixed(1)} pt at the ${report ? "report's" : `paper's ${fig.paper}`} width`);
  }
  if (fig.slide && Number.isFinite(text.px)) {
    const [bw, bh] = SLIDE_BOX[fig.slide];
    const px = text.px * Math.min(bw / size.w, bh / size.h);
    if (px < MIN_SLIDE_PX) ok = false;
    notes.push(`${Math.round(px)} px on a 1920 px slide (${fig.slide})`);
  }
  if (!Number.isFinite(text.px)) notes.push("no text");
  return { ok, notes };
}

async function main() {
  const args = process.argv.slice(2);
  const only = args.filter((a) => !a.startsWith("--"));
  const unknown = only.filter((n) => !FIGURES.some((f) => f.name === n));
  if (unknown.length) throw new Error(`unknown figure: ${unknown.join(", ")}`);
  if (!args.includes("--no-build") || !existsSync(join(SITE, "index.html"))) build();
  staticInter();
  mkdirSync(OUT, { recursive: true });
  const fontUrl = `data:font/woff2;base64,${readFileSync(FONT).toString("base64")}`;
  const date = pageDate();
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  let failed = 0;
  try {
    for (const fig of FIGURES.filter((f) => !only.length || only.includes(f.name))) {
      const out = await exportFigure(browser, base, fig, { fontUrl, date });
      const check = legibility(fig, out);
      if (IN_PAPER.includes(fig.name)) {
        mkdirSync(PAPER_OUT, { recursive: true });
        copyFileSync(join(OUT, `${fig.name}.pdf`), join(PAPER_OUT, `${fig.name}.pdf`));
      }
      if (!check.ok) failed++;
      if (out.fonts.type3 || (!out.fonts.embedded && Number.isFinite(out.text.px))) {
        failed++;
        check.notes.push(`PDF fonts: ${out.fonts.embedded} embedded, ${out.fonts.type3} Type 3`);
      }
      const kb = out.files.map((f) => `${extname(f).slice(1)} ${Math.round(statSync(f).size / 1024)} KB`).join(", ");
      const size = `${String(out.size.w).padStart(4)} x ${String(out.size.h).padEnd(4)} px`;
      const smallest = `smallest ${out.text.px.toFixed(1)} px ("${out.text.text}")`;
      const status = check.ok ? "ok  " : "FAIL";
      console.log(`${status} ${fig.name.padEnd(16)} ${size}  ${smallest}: ${check.notes.join("; ")}  [${kb}]`);
    }
  } finally {
    await browser.close();
    server.close();
  }
  console.log(`written to ${relative(process.cwd(), OUT)}, the paper's to ${relative(process.cwd(), PAPER_OUT)}`);
  if (failed) {
    console.error(`${failed} figure(s) below the legibility floor or without fonts`);
    process.exitCode = 1;
  }
}

await main();
