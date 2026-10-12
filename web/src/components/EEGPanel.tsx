import { useEffect, useRef } from "react";
import { PHASE_CODES, eegBuffer, type EegRing } from "../stream/eegBuffer";

// EEG chart paper: one row per display channel, the last 8 s, newest on the right, the
// background tinted by phase the way an EEG reviewer marks events. Drawn imperatively at
// most 30 times a second, and only when new samples arrived (no React state per sample).

const RANGE_UV = 20; // ± µV at full row height
const INK = "#161d24";
const MUTED = "#4b5761";
const GRID_MINOR = "#eceeee";
const GRID_MAJOR = "#d5dadc";
const SHADE: Record<number, string> = {
  [PHASE_CODES.rest]: "#f4f5f4",
  [PHASE_CODES.prepare]: "#f4ecd6",
};
const CUE_SHADE: Record<string, string> = { affected_hand: "#e3e9f9", sixth_finger: "#fbe5dd" };

export function paint(ctx: CanvasRenderingContext2D, ring: EegRing, w: number, h: number, dpr: number) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#fbfbfa";
  ctx.fillRect(0, 0, w, h);
  const labelW = 44;
  const plotW = w - labelW;
  const cap = ring.capacity || 1;
  const step = plotW / cap;
  const start = (ring.write - ring.filled + cap) % cap;
  const offset = cap - ring.filled; // empty space on the left before the buffer fills

  // Phase bands, merged into runs.
  let runStart = 0;
  for (let i = 0; i <= ring.filled; i++) {
    const idx = (start + i) % cap;
    const prev = (start + i - 1 + cap) % cap;
    const changed = i === ring.filled || (i > 0 && (ring.phase[idx] !== ring.phase[prev] || ring.truth[idx] !== ring.truth[prev]));
    if (changed) {
      const code = ring.phase[prev];
      const colour = code === PHASE_CODES.imagery ? CUE_SHADE[ring.truth[prev] ?? ""] : SHADE[code];
      if (colour) {
        ctx.fillStyle = colour;
        ctx.fillRect(labelW + (offset + runStart) * step, 0, (i - runStart) * step, h);
      }
      runStart = i;
    }
  }

  // Grid: a line every 0.2 s, stronger every second, fixed to the paper.
  const perSecond = ring.sfreq;
  for (let s = 0; s <= cap; s += perSecond / 5) {
    const major = Math.round(s) % Math.round(perSecond) === 0;
    ctx.strokeStyle = major ? GRID_MAJOR : GRID_MINOR;
    ctx.lineWidth = 1;
    const x = Math.round(labelW + s * step) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }

  const n = ring.channels.length;
  if (!n) return;
  const rowH = h / n;
  ctx.font = '500 12px "IBM Plex Mono", ui-monospace, monospace';
  ctx.textBaseline = "middle";
  for (let c = 0; c < n; c++) {
    const mid = rowH * (c + 0.5);
    ctx.fillStyle = MUTED;
    ctx.fillText(ring.channels[c], 6, mid);
    ctx.strokeStyle = GRID_MAJOR;
    ctx.beginPath();
    ctx.moveTo(labelW, Math.round(mid) + 0.5);
    ctx.lineTo(w, Math.round(mid) + 0.5);
    ctx.stroke();
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    const gain = (rowH * 0.45) / RANGE_UV;
    const row = ring.data[c];
    for (let i = 0; i < ring.filled; i++) {
      const v = Math.max(-RANGE_UV * 1.1, Math.min(RANGE_UV * 1.1, row[(start + i) % cap]));
      const x = labelW + (offset + i) * step;
      const y = mid - v * gain;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // Scale: 1 s and 20 µV, bottom right, on a patch of paper so no trace runs through it.
  const bx = w - 12 - perSecond * step;
  const by = h - 10;
  ctx.fillStyle = "rgba(251, 251, 250, 0.94)";
  ctx.fillRect(bx - 46, by - rowH * 0.45 - 4, perSecond * step + 54, rowH * 0.45 + 10);
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(bx, by - rowH * 0.45);
  ctx.lineTo(bx, by);
  ctx.lineTo(bx + perSecond * step, by);
  ctx.stroke();
  ctx.fillStyle = INK;
  ctx.font = '12px "IBM Plex Mono", ui-monospace, monospace';
  ctx.textBaseline = "bottom";
  ctx.textAlign = "right";
  ctx.fillText("1 s", bx + perSecond * step, by - 3);
  ctx.textBaseline = "middle";
  ctx.fillText(`${RANGE_UV} µV`, bx - 6, by - (rowH * 0.45) / 2);
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
