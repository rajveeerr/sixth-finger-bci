import { useEffect, useMemo, useRef, useState, type CSSProperties, type FocusEvent, type KeyboardEvent } from "react";
import { Plate } from "../../components/Plate";
import { damp } from "../../hands/spring";
import { shownCommand, useDemo, type Command } from "../../store";
import { eegBuffer } from "../../stream/eegBuffer";
import {
  buildChain,
  fingerPoints,
  LIFT,
  LINK_R,
  PAPER_Z,
  PARTS,
  PEN_X,
  project,
  PX_PER_S,
  ROW_Y,
  SECONDS,
  UNIT,
  VIEW_H,
  VIEW_W,
  P,
  type Layer,
  type PartId,
} from "../iso/chain";
import { axisVector } from "../iso/kit";

const LAMP_OF: Record<Command, string> = { IDLE: "rest", HAND_GRASP: "affected_hand", SIXTH_FINGER_FLEX: "sixth_finger" };
const OPEN = [0.08, 0.06, 0.04];
const FLEXED = [0.95, 0.85, 0.65];
const GAIN = 0.18; // paper units per µV: ±20 µV fills a row
const RANGE = 22;

/** The ink on the paper: the newest 4 s (inside the frame) and the older ink beyond it. */
function inkPaths(): [string, string] {
  const ring = eegBuffer;
  const cap = ring.capacity;
  if (!cap || !ring.filled) return ["", ""];
  const o = project([0, 0, PAPER_Z]);
  const ux = axisVector(P, [1, 0, 0]);
  const uy = axisVector(P, [0, 1, 0]);
  const newest = (ring.write - 1 + cap) % cap;
  const fresh: string[] = [];
  const old: string[] = [];
  const step = 2;
  for (let c = 0; c < Math.min(ring.data.length, ROW_Y.length); c++) {
    const row = ring.data[c];
    let a = "";
    let b = "";
    for (let i = 0; i < ring.filled; i += step) {
      const age = i / ring.sfreq;
      if (age > SECONDS) break;
      const v = Math.max(-RANGE, Math.min(RANGE, row[(newest - i + cap) % cap]));
      const x = PEN_X + age * PX_PER_S;
      const y = ROW_Y[c] + v * GAIN;
      const sx = (o[0] + x * ux[0] + y * uy[0]).toFixed(1);
      const sy = (o[1] + x * ux[1] + y * uy[1]).toFixed(1);
      if (age <= 4) a += `${a ? "L" : "M"}${sx} ${sy}`;
      if (age >= 4 - (step / ring.sfreq) * 1.01) b += `${b ? "L" : "M"}${sx} ${sy}`;
    }
    fresh.push(a);
    old.push(b);
  }
  return [fresh.join(""), old.join("")];
}

/** How a run of the bench answers a part: rise with it, bend a wire's end with it, or stay bright where it is. */
function modeOf(layer: Layer, part: PartId) {
  if (layer.kind === "wire") return layer.part === part ? "from" : layer.to === part ? "to" : undefined;
  if (layer.hold === part) return "hold";
  if (layer.part !== part) return undefined;
  return layer.kind === "part" || layer.kind === "shadow" ? "up" : "hold";
}

/** The part under the pointer: its drawing, the hit area under it, its shadow or its pin. */
function partAt(target: EventTarget | null) {
  const el = (target as Element | null)?.closest?.("[data-hit]");
  return el ? Number(el.getAttribute("data-hit")) : null;
}

const STEP: Record<string, (i: number) => number> = {
  ArrowRight: (i) => i + 1,
  ArrowDown: (i) => i + 1,
  ArrowLeft: (i) => i - 1,
  ArrowUp: (i) => i - 1,
  Home: () => 0,
  End: () => PARTS.length - 1,
};

/**
 * The signal chain as a bench instrument. It is live: the paper carries the demo's EEG, the
 * lit lamp is the demo's command, and the finger moves with the demo's hand.
 */
export function SignalChain() {
  const art = useMemo(() => buildChain(), []);
  const command = useDemo(shownCommand);
  const svg = useRef<SVGSVGElement>(null);
  const inkNew = useRef<SVGPathElement>(null);
  const inkOld = useRef<SVGPathElement>(null);
  const links = useRef<(SVGPathElement | null)[]>([]);
  const joints = useRef<(SVGCircleElement | null)[]>([]);
  const target = useRef(OPEN);
  const angles = useRef([...OPEN]);

  useEffect(() => {
    target.current = command === "SIXTH_FINGER_FLEX" ? FLEXED : OPEN;
  }, [command]);

  useEffect(() => {
    const root = svg.current;
    if (!root) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let visible = false;
    let drawn = -1;
    let last = 0;
    let prev = performance.now();
    const drawFinger = () => {
      const pts = fingerPoints(angles.current).map(project);
      links.current.forEach((el, i) => {
        if (!el) return;
        const k = i % 3;
        el.setAttribute("d", `M${pts[k][0].toFixed(1)} ${pts[k][1].toFixed(1)}L${pts[k + 1][0].toFixed(1)} ${pts[k + 1][1].toFixed(1)}`);
      });
      joints.current.forEach((el, i) => {
        if (!el) return;
        el.setAttribute("cx", pts[i][0].toFixed(1));
        el.setAttribute("cy", pts[i][1].toFixed(1));
      });
    };
    const frame = (now: number) => {
      raf = visible ? requestAnimationFrame(frame) : 0;
      const dt = Math.min((now - prev) / 1000, 0.1);
      prev = now;
      let moving = false;
      angles.current = angles.current.map((a, i) => {
        const next = still ? target.current[i] : damp(a, target.current[i], 9, dt);
        if (Math.abs(next - target.current[i]) > 1e-3) moving = true;
        return next;
      });
      if (moving || drawn === -1) drawFinger();
      if (now - last < 33 || eegBuffer.version === drawn) return;
      last = now;
      drawn = eegBuffer.version;
      const [a, b] = inkPaths();
      inkNew.current?.setAttribute("d", a);
      inkOld.current?.setAttribute("d", b);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !raf) {
        prev = performance.now();
        raf = requestAnimationFrame(frame);
      }
    });
    observer.observe(root);
    drawFinger();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, []);

  const lit = LAMP_OF[command];
  const [part, setPart] = useState<number | null>(null);
  const on = part === null ? undefined : PARTS[part].id;
  // The part let go of stays bright while the rest fades back, and the dimming filter stays
  // on until that fade is over, so nothing blinks.
  const [last, setLast] = useState<PartId>();
  const [dim, setDim] = useState(false);
  if (on && (on !== last || !dim)) {
    setLast(on);
    setDim(true);
  }
  useEffect(() => {
    if (on || !dim) return;
    const t = window.setTimeout(() => setDim(false), 300);
    return () => window.clearTimeout(t);
  }, [on, dim]);
  const liftOf = (layer: Layer) => (on ? modeOf(layer, on) : last && modeOf(layer, last) ? "hold" : undefined);
  const pins = useMemo(() => PARTS.map((p) => project(p.at)), []);
  // Everything about a run but whether it is lifted, so a pick only touches attributes, never the drawing.
  const runs = useMemo(
    () =>
      art.layers.map((layer) => ({
        layer,
        html: layer.live ? undefined : { __html: layer.svg },
        className: layer.kind === "hits" ? "part-hits" : layer.kind === "shadow" ? "part-shadow" : `piece piece-${layer.kind}`,
        hit: layer.kind === "part" || layer.kind === "shadow" ? PARTS.findIndex((p) => p.id === layer.part) : undefined,
        style: layer.bend ? ({ "--bend-from": layer.bend[0], "--bend-to": layer.bend[1] } as CSSProperties) : undefined,
      })),
    [art],
  );
  const live = (name: Layer["live"]) => {
    if (name === "ink-old") return <path ref={inkOld} className="ink ink-old" />;
    if (name === "ink-new") return <path ref={inkNew} className="ink ink-new" />;
    return (
      <g className="finger" data-active={command === "SIXTH_FINGER_FLEX" ? "" : undefined}>
        {[0, 1, 2].map((i) => (
          <path key={`o${i}`} ref={(el) => { links.current[i] = el; }} className="link-edge"
            strokeWidth={LINK_R[i] * 2 * UNIT + 1.8} />
        ))}
        {[0, 1, 2].map((i) => (
          <path key={`f${i}`} ref={(el) => { links.current[3 + i] = el; }} className="link-body"
            strokeWidth={LINK_R[i] * 2 * UNIT} />
        ))}
        {[0, 1, 2].map((i) => (
          <path key={`s${i}`} ref={(el) => { links.current[6 + i] = el; }} className="link-strip"
            strokeWidth={2 * UNIT} />
        ))}
        {[0, 1, 2, 3].map((i) => (
          <circle key={i} ref={(el) => { joints.current[i] = el; }} r={(i === 3 ? 3.4 : 1.7) * UNIT}
            className={i === 3 ? "link-tip" : "link-pin"} />
        ))}
      </g>
    );
  };
  // One tab stop per row of controls; the arrow keys walk the parts within it.
  const stop = part ?? 0;
  const walk = (i: number) => (e: KeyboardEvent<HTMLElement | SVGElement>) => {
    const to = STEP[e.key]?.(i);
    if (to === undefined) return;
    e.preventDefault();
    const row = e.currentTarget.closest("svg, ol")?.querySelectorAll<HTMLElement | SVGElement>("[tabindex]");
    row?.[(to + PARTS.length) % PARTS.length]?.focus();
  };
  const leave = (e: FocusEvent) => {
    if (partAt(e.relatedTarget) === null) setPart(null);
  };
  return (
    <Plate
        title="The whole system on one bench"
        hint="It moves with the live demo further down."
        readout={part === null ? "Point at or tap a part to lift it off the bench and see what it does." : <><b>{PARTS[part].name}.</b> {PARTS[part].text}</>}
        className="plate-chain bleed"
      >
        <svg
          ref={svg}
          className="iso-svg chain dotted"
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          role="group"
          aria-label="A bench model of the signal chain: head with electrodes, amplifier, paper with EEG, a 4 s frame, the decoder with three lamps and the robotic finger"
          data-lit={lit}
          data-on={on}
          data-dim={dim ? "" : undefined}
          style={{ "--lift": `${-LIFT}px` } as CSSProperties}
          onPointerOver={(e) => e.pointerType !== "touch" && setPart(partAt(e.target))}
          onPointerLeave={(e) => e.pointerType === "mouse" && setPart(null)}
          onClick={(e) => setPart(partAt(e.target))}
        >
          <defs>
            <filter id="chain-dim" colorInterpolationFilters="sRGB" x="-10%" y="-25%" width="120%" height="150%">
              <feFlood className="chain-dim" />
              <feComposite in2="SourceGraphic" operator="in" />
              <feComposite in2="SourceGraphic" operator="over" />
            </filter>
          </defs>
          {runs.map(({ layer, html, className, hit, style }, i) => (
            <g key={i} className={className} data-hit={hit} data-lift={liftOf(layer)} style={style} dangerouslySetInnerHTML={html}>
              {layer.live ? live(layer.live) : undefined}
            </g>
          ))}
          {pins.map(([x, y], i) => (
            <g key={PARTS[i].id} className="part-pin" data-hit={i}
              data-on={part === i ? "" : undefined} tabIndex={i === stop ? 0 : -1} role="button" aria-pressed={part === i}
              aria-label={`${PARTS[i].name}: ${PARTS[i].text}`}
              onFocus={() => setPart(i)} onBlur={leave} onKeyDown={walk(i)}>
              <circle cx={x} cy={y} r={13} />
              <text x={x} y={y + 4.5} textAnchor="middle">{i + 1}</text>
            </g>
          ))}
        </svg>
        <ol className="part-names">
          {PARTS.map((p, i) => (
            <li key={p.id}>
              <button type="button" data-hit={i} data-on={part === i ? "" : undefined}
                aria-pressed={part === i} tabIndex={i === stop ? 0 : -1}
                onPointerEnter={(e) => e.pointerType !== "touch" && setPart(i)}
                onPointerLeave={(e) => e.pointerType === "mouse" && setPart(null)}
                onFocus={() => setPart(i)} onBlur={leave} onClick={() => setPart(i)} onKeyDown={walk(i)}>
                <b>{i + 1}</b> {p.name}
              </button>
            </li>
          ))}
        </ol>
      </Plate>
  );
}
