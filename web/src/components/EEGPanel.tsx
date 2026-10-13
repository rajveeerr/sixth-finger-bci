import { useEffect, useRef } from "react";
import { PHASE_CODES, eegBuffer, type EegRing } from "../stream/eegBuffer";

// The brain signal, kept to what a first-time viewer can follow: three sensors over the
// hand area (left, middle, right of the head), the last 8 s, newest on the right. While
// the patient imagines, the paper is faintly tinted. New signal comes in at the right edge
// and moves left through a fixed frame over the newest 4 s, which is what the model reads;
// each reading stamps the frame and the stamp moves on with the paper. Drawn at most 30 times a second, and only when
// something changed (no React state per sample).

const SHOWN = ["C3", "Cz", "C4"];
const NAMES: Record<string, string> = { C3: "left", Cz: "middle", C4: "right" };
const RANGE_UV = 28; // ± µV at a row's half height
const FONT = '500 12px "Inter Variable", Inter, system-ui, sans-serif';
const SMALL = '450 11px "Inter Variable", Inter, system-ui, sans-serif';
const INK = "#171717";
const MUTED = "#707070";
const SECOND = "#efefef";
const PAPER = "#fafafa";
const TINT: Record<string, string> = { affected_hand: "#f1f1f1", sixth_finger: "#fff3ed" };
const KIND_COLOUR: Record<string, string> = {
  rest: "#707070",
  affected_hand: "#3a3a3a",
  sixth_finger: "#d9480f",
  imagery: "#d9480f",
};
const SAY: Record<string, string> = { rest: "Rest", affected_hand: "Hand", sixth_finger: "Sixth finger", imagery: "Imagining" };

function imageryAt(ring: EegRing, idx: number): string | null {
  return ring.phase[idx] === PHASE_CODES.imagery ? (ring.truth[idx] ?? "imagery") : null;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function paint(ctx: CanvasRenderingContext2D, ring: EegRing, w: number, h: number, dpr: number) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, w, h);
  const labelW = 58;
  const top = 36; // room for the reading's tab
  const bottom = h - 22; // room for the time scale
  const plotW = w - labelW - 6;
  const plotH = bottom - top;
  const cap = ring.capacity || 1;
  const step = plotW / cap;
  const start = (ring.write - ring.filled + cap) % cap;
  const offset = cap - ring.filled;
  const xOf = (i: number) => labelW + (offset + i) * step;

  // Imagining: a faint tint over the stretch where the patient was asked to imagine.
  let runStart = 0;
  for (let i = 1; i <= ring.filled; i++) {
    const prev = imageryAt(ring, (start + i - 1) % cap);
    if (i < ring.filled && imageryAt(ring, (start + i) % cap) === prev) continue;
    if (prev && TINT[prev]) {
      ctx.fillStyle = TINT[prev];
      ctx.fillRect(xOf(runStart), top - 8, xOf(i) - xOf(runStart), plotH + 8);
    }
    runStart = i;
  }

  // A hairline every second, moving with the paper.
  const perSecond = ring.sfreq;
  const phase = (ring.total % perSecond) / perSecond;
  ctx.fillStyle = SECOND;
  for (let k = 0; k <= cap / perSecond + 1; k++) {
    const x = Math.round(labelW + (k - phase) * perSecond * step);
    if (x >= labelW && x <= labelW + plotW) ctx.fillRect(x, top - 8, 1, plotH + 8);
  }

  // The three traces, each named by its sensor and its side of the head.
  const rows = SHOWN.map((name) => ring.channels.indexOf(name)).filter((c) => c >= 0);
  const rowH = rows.length ? plotH / rows.length : plotH;
  ctx.textBaseline = "middle";
  rows.forEach((c, r) => {
    const mid = top + rowH * (r + 0.5);
    ctx.textAlign = "left";
    ctx.font = FONT;
    ctx.fillStyle = INK;
    ctx.fillText(ring.channels[c], 0, mid - 7);
    ctx.font = SMALL;
    ctx.fillStyle = MUTED;
    ctx.fillText(NAMES[ring.channels[c]] ?? "", 0, mid + 8);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1.1;
    ctx.lineJoin = "round";
    ctx.beginPath();
    const gain = (rowH * 0.42) / RANGE_UV;
    const row = ring.data[c];
    for (let i = 0; i < ring.filled; i++) {
      const v = Math.max(-RANGE_UV * 1.15, Math.min(RANGE_UV * 1.15, row[(start + i) % cap]));
      const x = xOf(i);
      const y = mid - v * gain;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });

  // The reading frame: fixed over the newest 4 s at the right, where the signal comes in.
  // When the model reads, the frame is stamped with its reading and the stamp travels left
  // with the paper; older stamps fade as they go.
  const first = ring.total - ring.filled;
  const winLen = ring.marks[ring.marks.length - 1]?.len ?? Math.round(4 * ring.sfreq);
  const right = labelW + plotW;
  const fx0 = right - winLen * step;
  const newest = ring.marks[ring.marks.length - 1];
  const justRead = newest && ring.total - newest.end < ring.sfreq * 1.2;
  ctx.font = FONT;
  ctx.textAlign = "left";
  ring.marks.forEach((m, j) => {
    const x1 = xOf(m.end - first);
    const x0 = Math.max(xOf(m.end - m.len - first), labelW);
    if (x1 < labelW + 20) return;
    const read = ring.view === "switch" ? m.switch : m.three;
    const colour = KIND_COLOUR[read.kind] ?? INK;
    const age = ring.marks.length - 1 - j;
    ctx.globalAlpha = age === 0 ? 1 : 0.45;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 1.5;
    roundRect(ctx, x0, top - 6, x1 - x0, plotH + 4, 6);
    ctx.stroke();
    const text = `${age === 0 && justRead ? "Model read: " : ""}${SAY[read.kind] ?? read.kind} ${read.right === null ? "" : read.right ? "✓" : "✗"}`;
    const tw = ctx.measureText(text).width + 16;
    const tx = Math.min(x0, w - tw - 2);
    ctx.fillStyle = colour;
    roundRect(ctx, tx, top - 32, tw, 22, 5);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, tx + 8, top - 21);
    ctx.globalAlpha = 1;
  });
  if (!justRead) {
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = MUTED;
    ctx.lineWidth = 1.2;
    roundRect(ctx, fx0, top - 6, right - fx0, plotH + 4, 6);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = MUTED;
    ctx.textAlign = "right";
    ctx.fillText("The model reads the newest 4 s", right, top - 21);
    ctx.textAlign = "left";
  }

  // Where the signal comes in, and 1 second of time.
  ctx.font = SMALL;
  ctx.fillStyle = MUTED;
  if (ring.filled) {
    const xn = Math.round(xOf(ring.filled - 1));
    ctx.fillStyle = INK;
    ctx.fillRect(xn, top - 8, 1.5, plotH + 8);
    ctx.fillStyle = MUTED;
    ctx.textAlign = "right";
    ctx.fillText("new signal comes in here", xn, h - 8);
    const tw = ctx.measureText("new signal comes in here").width;
    ctx.fillRect(xn - tw - 30, h - 8.5, 20, 1.2);
    ctx.beginPath();
    ctx.moveTo(xn - tw - 30, h - 8);
    ctx.lineTo(xn - tw - 25, h - 11);
    ctx.lineTo(xn - tw - 25, h - 5);
    ctx.fill();
  }
  ctx.fillRect(labelW, h - 9, perSecond * step, 1.5);
  ctx.textAlign = "left";
  ctx.fillText("1 second", labelW + perSecond * step + 6, h - 8);
}

export function EEGPanel() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let last = 0;
    let drawn = -1;
    let size = { w: 0, h: 0, dpr: 1 };
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      size = { w: canvas.clientWidth, h: canvas.clientHeight, dpr };
      canvas.width = Math.round(size.w * dpr);
      canvas.height = Math.round(size.h * dpr);
      drawn = -1;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();
    // Paint only while the panel is on screen; off screen the loop sleeps.
    let visible = false;
    const frame = (now: number) => {
      raf = visible ? requestAnimationFrame(frame) : 0;
      if (now - last < 33 || eegBuffer.version === drawn || !size.w) return;
      last = now;
      drawn = eegBuffer.version;
      paint(ctx, eegBuffer, size.w, size.h, size.dpr);
    };
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !raf) raf = requestAnimationFrame(frame);
    });
    seen.observe(canvas);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      seen.disconnect();
    };
  }, []);
  return (
    <canvas
      ref={canvasRef}
      className="eeg-canvas"
      data-testid="eeg-panel"
      role="img"
      aria-label="EEG from three sensors over the hand area, the last eight seconds, with the piece the model read last boxed"
    />
  );
}
