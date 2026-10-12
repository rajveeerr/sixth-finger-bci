import { useEffect, useRef } from "react";
import { PHASE_CODES, eegBuffer, type EegRing } from "../stream/eegBuffer";

// EEG chart paper: one row per display channel, the last 8 s, newest on the right. A band
// along the top shows what the patient was asked to do, and a bracket marks each 4 s piece
// the model read, with what it read and whether that was right. Drawn imperatively at most
// 30 times a second, and only when something changed (no React state per sample).

const RANGE_UV = 26; // ± µV at a full row's half height
const FONT = '11px "Departure Mono", ui-monospace, monospace';
const INK = "#1a1f25";
const MUTED = "#8b929b";
const DOT = "#d5d9df";
const SECOND = "#eef0f2";
const PAPER = "#ffffff";
const TINT: Record<string, string> = { ready: "#fbf6e8", affected_hand: "#f4f6ff", sixth_finger: "#fff5f0" };
const BAND: Record<string, string> = { rest: "#e3e6ea", ready: "#e9c770", affected_hand: "#1342ff", sixth_finger: "#ff5a1f" };
const KIND_COLOUR: Record<string, string> = {
  rest: "#6f7780",
  affected_hand: "#1342ff",
  sixth_finger: "#d63d0b",
  imagery: "#d63d0b",
};
const SAY: Record<string, string> = { rest: "Rest", affected_hand: "Hand", sixth_finger: "Sixth finger", imagery: "Move" };

/** The phase key of a sample: rest, ready, or the imagery cue. */
function keyOf(ring: EegRing, idx: number): string {
  const code = ring.phase[idx];
  if (code === PHASE_CODES.prepare) return "ready";
  if (code === PHASE_CODES.imagery) return ring.truth[idx] ?? "imagery";
  return "rest";
}

export function paint(ctx: CanvasRenderingContext2D, ring: EegRing, w: number, h: number, dpr: number) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, w, h);
  const labelW = 46;
  const top = 30; // room for the instruction band and the read brackets
  const plotW = w - labelW - 10;
  const plotH = h - top - 22;
  const cap = ring.capacity || 1;
  const step = plotW / cap;
  const start = (ring.write - ring.filled + cap) % cap;
  const offset = cap - ring.filled; // empty paper on the left until the buffer fills
  const xOf = (i: number) => labelW + (offset + i) * step; // i: 0 = oldest sample on screen

  // What the patient was asked to do: a light tint behind the traces and a band on top.
  let runStart = 0;
  for (let i = 1; i <= ring.filled; i++) {
    const prev = keyOf(ring, (start + i - 1) % cap);
    if (i < ring.filled && keyOf(ring, (start + i) % cap) === prev) continue;
    const x0 = xOf(runStart);
    const x1 = xOf(i);
    if (TINT[prev]) {
      ctx.fillStyle = TINT[prev];
      ctx.fillRect(x0, top, x1 - x0, plotH);
    }
    ctx.fillStyle = BAND[prev] ?? BAND.rest;
    ctx.fillRect(x0, 4, x1 - x0, 4);
    runStart = i;
  }

  // The paper: a hairline every second and a dot every fifth of a second along each row.
  const n = ring.channels.length;
  const rowH = n ? plotH / n : plotH;
  const perSecond = ring.sfreq;
  const phase = (ring.total % perSecond) / perSecond; // the grid moves with the paper
  for (let k = -1; k <= cap / perSecond + 1; k++) {
    const x = Math.round(labelW + (k - phase + 1) * perSecond * step) + 0.5;
    if (x < labelW || x > labelW + plotW) continue;
    ctx.fillStyle = SECOND;
    ctx.fillRect(x, top, 1, plotH);
  }
  ctx.fillStyle = DOT;
  for (let c = 0; c < n; c++) {
    const y = Math.round(top + rowH * (c + 0.5));
    for (let k = 0; k <= (cap / perSecond) * 5 + 5; k++) {
      const x = labelW + (k / 5 - phase + 1) * perSecond * step;
      if (x < labelW || x > labelW + plotW) continue;
      ctx.fillRect(Math.round(x), y, 1.5, 1.5);
    }
  }

  // The brackets: each 4 s piece the model read, with its reading and a tick or cross.
  ctx.font = FONT;
  ctx.textBaseline = "middle";
  const first = ring.total - ring.filled;
  ring.marks.forEach((m, j) => {
    const x1 = xOf(m.end - first);
    const x0 = xOf(m.end - m.len - first);
    if (x1 < labelW) return;
    const read = ring.view === "switch" ? m.switch : m.three;
    const colour = KIND_COLOUR[read.kind] ?? INK;
    const newest = j === ring.marks.length - 1;
    ctx.globalAlpha = newest ? 1 : 0.55;
    ctx.fillStyle = colour;
    ctx.globalAlpha *= 0.06;
    ctx.fillRect(Math.max(x0, labelW), top, x1 - Math.max(x0, labelW), plotH);
    ctx.globalAlpha = newest ? 1 : 0.55;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const y = 15;
    ctx.moveTo(Math.max(x0, labelW), y + 7);
    ctx.lineTo(Math.max(x0, labelW), y);
    ctx.lineTo(x1, y);
    ctx.lineTo(x1, y + 7);
    ctx.stroke();
    const text = `read: ${SAY[read.kind] ?? read.kind} ${read.right === null ? "" : read.right ? "✓" : "✗"}`;
    const tw = ctx.measureText(text).width + 10;
    const tx = Math.min(Math.max((Math.max(x0, labelW) + x1) / 2 - tw / 2, labelW), w - tw - 4);
    ctx.fillStyle = PAPER;
    ctx.fillRect(tx, y - 7, tw, 14);
    ctx.fillStyle = colour;
    ctx.fillText(text, tx + 5, y + 0.5);
    ctx.globalAlpha = 1;
  });

  // The traces, and the channel names in the margin.
  for (let c = 0; c < n; c++) {
    const mid = top + rowH * (c + 0.5);
    ctx.fillStyle = MUTED;
    ctx.textAlign = "left";
    ctx.fillText(ring.channels[c], 8, mid);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1;
    ctx.lineJoin = "round";
    ctx.beginPath();
    const gain = (rowH * 0.48) / RANGE_UV;
    const row = ring.data[c];
    for (let i = 0; i < ring.filled; i++) {
      const v = Math.max(-RANGE_UV * 1.15, Math.min(RANGE_UV * 1.15, row[(start + i) % cap]));
      const x = xOf(i);
      const y = mid - v * gain;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // Now, at the right edge, and the scale: 1 s across, 20 µV up.
  if (ring.filled) {
    const xn = xOf(ring.filled - 1);
    ctx.fillStyle = INK;
    ctx.fillRect(Math.round(xn), top, 1, plotH);
  }
  // 1 s along the bottom right; 20 µV up the margin beside the last row.
  const sx = labelW + plotW - perSecond * step;
  const sy = h - 8;
  ctx.fillStyle = INK;
  ctx.fillRect(sx, sy, perSecond * step, 1.5);
  ctx.fillStyle = MUTED;
  ctx.textAlign = "right";
  ctx.fillText("1 s", sx - 6, sy);
  if (n) {
    const bar = (20 / RANGE_UV) * rowH * 0.48;
    const mid = top + rowH * (n - 0.5);
    ctx.fillStyle = INK;
    ctx.fillRect(labelW - 6, mid - bar / 2, 1.5, bar);
    ctx.fillStyle = MUTED;
    ctx.textAlign = "left";
    ctx.fillText("20 µV", 8, h - 8);
  }
  ctx.textAlign = "left";
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
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (now - last < 33 || eegBuffer.version === drawn || !size.w) return;
      last = now;
      drawn = eegBuffer.version;
      paint(ctx, eegBuffer, size.w, size.h, size.dpr);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);
  return (
    <canvas
      ref={canvasRef}
      className="eeg-canvas"
      data-testid="eeg-panel"
      role="img"
      aria-label="EEG of seven channels over the motor cortex, the last eight seconds"
    />
  );
}
