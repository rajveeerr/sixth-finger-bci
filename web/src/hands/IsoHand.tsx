import { useEffect, useId, useMemo, useRef } from "react";
import type { Command } from "../store";
import { POSES } from "./poses";
import { damp } from "./spring";
import * as K from "../explain/iso/kit";
import {
  behindPalm,
  centroid,
  HOUSING,
  PALM,
  pieces,
  STRAP,
  WRIST,
  type P3,
  type Piece,
} from "./rig";

// The hand as an isometric drawing in the bench's finish. The fixed parts are
// drawn once with the drawing core; the moving pieces (segments, knuckles, the robotic
// links) are round, so each is a stadium or a circle with tone bands, sorted by depth
// and redrawn only while the hand moves.

const W = 420;
const H = 470;
export const AZIMUTH = 55;
const PLINTH = { r: 6.8, z0: -9.6, h: 1.3 };

const P = K.fitProjection(
  [
    ...K.boxCorners({ x: -PLINTH.r, y: -PLINTH.r, w: 2 * PLINTH.r, d: 2 * PLINTH.r, r: 0 }, PLINTH.z0, PLINTH.z0 + PLINTH.h),
    [0, 0, 19],
    [-10, -1.5, 9],
    [9, -4, 6],
  ],
  W,
  H,
  { pad: 16, azimuth: AZIMUTH },
);
const UNIT = Math.abs(K.axisVector(P, [0, 0, 1])[1]) / Math.cos(Math.PI / 6);
const at = (p: P3) => K.iso(p, P);
const f1 = (v: number) => v.toFixed(1);

// Where the light comes from on screen: the kit lights faces turned toward (−sin A, cos A).
const LIGHT = (() => {
  const a = (AZIMUTH * Math.PI) / 180;
  const [x, y] = K.axisVector(P, [-Math.sin(a), Math.cos(a), 0.9]);
  const n = Math.hypot(x, y);
  return [x / n, y / n] as const;
})();

const ellipse = (rx: number, ry: number, steps = 48): K.Plane[] =>
  Array.from({ length: steps }, (_, i) => {
    const t = (i / steps) * Math.PI * 2;
    return [rx * Math.cos(t), ry * Math.sin(t)] as K.Plane;
  });

function staticArt() {
  const back: string[] = [];
  back.push(K.solidSvg(K.cylinder(0, 0, PLINTH.r, PLINTH.z0, PLINTH.h, P, 64, 0.8), { tone: "mid", halo: true }));
  const ticks = K.radialTicks(0, 0, PLINTH.r - 0.5, 60, 5, PLINTH.z0 + PLINTH.h, [0.5, 1.1], P);
  back.push(K.lineSvg(ticks.minor, { tone: "lo" }), K.lineSvg(ticks.major, { tone: "mid" }));
  back.push(K.solidSvg(K.cylinder(0, 0, WRIST.rx + 0.6, PLINTH.z0 + PLINTH.h, 0.5, P, 64, 0.3), { tone: "mid" }));
  back.push(K.solidSvg(K.extrude(ellipse(WRIST.rx, WRIST.ry), PLINTH.z0 + PLINTH.h + 0.5, -(PLINTH.z0 + PLINTH.h + 0.5) + 0.6, P), { tone: "hi" }));
  const band = ellipse(WRIST.rx + STRAP.grow, WRIST.ry + STRAP.grow);
  back.push(K.solidSvg(K.extrude(band, STRAP.z0, STRAP.h, P), { tone: "hi", className: "strap" }));
  back.push(K.lineSvg(K.ringSeam(band, STRAP.z0 + 0.3, P), { tone: "mid", dashed: true }));
  back.push(K.lineSvg(K.ringSeam(band, STRAP.z0 + STRAP.h - 0.3, P), { tone: "mid", dashed: true }));
  const palm: K.Plan = { x: -PALM.w / 2, y: -PALM.d / 2, w: PALM.w, d: PALM.d, r: PALM.r };
  const palmSvg = K.solidSvg(K.slabOf(palm, 0, PALM.h, P, 10, 0.5), { tone: "hi" });
  const housing: K.Plan = { x: HOUSING.x, y: HOUSING.y, w: HOUSING.w, d: HOUSING.d, r: 0.4 };
  const front = [
    K.solidSvg(K.slabOf(housing, HOUSING.z0, HOUSING.h, P, 6, 0.3), { tone: "hi" }),
    K.lineSvg(K.sideSeam(housing, HOUSING.z0 + HOUSING.h - 0.5, P), { tone: "faint" }),
    K.dotsSvg(
      [
        [HOUSING.x + HOUSING.w, HOUSING.y + 0.45, HOUSING.z0 + 0.5],
        [HOUSING.x + HOUSING.w, HOUSING.y + HOUSING.d - 0.45, HOUSING.z0 + 0.5],
        [HOUSING.x + HOUSING.w, HOUSING.y + 0.45, HOUSING.z0 + HOUSING.h - 0.9],
        [HOUSING.x + HOUSING.w, HOUSING.y + HOUSING.d - 0.45, HOUSING.z0 + HOUSING.h - 0.9],
      ].map((p) => at(p as P3)),
      { size: 0.9, tone: "hi" },
    ),
  ].join("");
  return { back: back.join(""), palm: palmSvg, housing: front };
}

/** A round segment seen in this projection: a stadium, with bands on its shadowed side. */
function stadium(a: K.Flat, b: K.Flat) {
  let dx = b[0] - a[0];
  let dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len < 1e-3) {
    dx = 0;
    dy = 1;
  } else {
    dx /= len;
    dy /= len;
  }
  let nx = -dy;
  let ny = dx;
  if (nx * LIGHT[0] + ny * LIGHT[1] > 0) {
    nx = -nx;
    ny = -ny;
  } // n now points to the shadowed side
  const path = (o: number, rr: number) => {
    const ax = a[0] + nx * o;
    const ay = a[1] + ny * o;
    const bx = b[0] + nx * o;
    const by = b[1] + ny * o;
    return `M${f1(ax + nx * rr)} ${f1(ay + ny * rr)}L${f1(bx + nx * rr)} ${f1(by + ny * rr)}A${f1(rr)} ${f1(rr)} 0 0 0 ${f1(bx - nx * rr)} ${f1(by - ny * rr)}L${f1(ax - nx * rr)} ${f1(ay - ny * rr)}A${f1(rr)} ${f1(rr)} 0 0 0 ${f1(ax + nx * rr)} ${f1(ay + ny * rr)}Z`;
  };
  return { path, n: [nx, ny] as const };
}

function pieceSvg(p: Piece, id: string, lit: boolean): string {
  if (p.kind === "ball") {
    const [cx, cy] = at(p.c);
    const r = p.r * UNIT;
    const sx = -LIGHT[0];
    const sy = -LIGHT[1];
    return (
      `<g class="ih-ball"><clipPath id="${id}"><circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}"/></clipPath>` +
      `<circle class="ih-body" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}"/>` +
      `<g clip-path="url(#${id})"><circle class="ih-shade1" cx="${f1(cx + sx * r * 0.75)}" cy="${f1(cy + sy * r * 0.75)}" r="${f1(r * 0.75)}"/>` +
      `<circle class="ih-shade0" cx="${f1(cx + sx * r * 1.05)}" cy="${f1(cy + sy * r * 1.05)}" r="${f1(r * 0.55)}"/></g>` +
      `<circle class="ih-edge" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}"/></g>`
    );
  }
  const a = at(p.a);
  const b = at(p.b);
  const r = p.r * UNIT;
  const s = stadium(a, b);
  const body = s.path(0, r);
  let out =
    `<g class="${p.kind === "link" ? "ih-link" : "ih-seg"}"><clipPath id="${id}"><path d="${body}"/></clipPath>` +
    `<path class="ih-body" d="${body}"/><g clip-path="url(#${id})">` +
    `<path class="ih-shade1" d="${s.path(r * 0.75, r * 0.6)}"/><path class="ih-shade0" d="${s.path(r * 1.05, r * 0.35)}"/></g>`;
  if (p.kind === "link") {
    // the robotic link: a light strip down its back and the steel pin at its joint
    const sa: K.Flat = [a[0] - s.n[0] * r * 0.35, a[1] - s.n[1] * r * 0.35];
    const sb: K.Flat = [b[0] - s.n[0] * r * 0.35, b[1] - s.n[1] * r * 0.35];
    const t = 0.22;
    const ia: K.Flat = [sa[0] + (sb[0] - sa[0]) * t, sa[1] + (sb[1] - sa[1]) * t];
    const ib: K.Flat = [sa[0] + (sb[0] - sa[0]) * (1 - t), sa[1] + (sb[1] - sa[1]) * (1 - t)];
    out += `<path class="ih-strip${lit ? " on" : ""}" d="M${f1(ia[0])} ${f1(ia[1])}L${f1(ib[0])} ${f1(ib[1])}" stroke-width="${f1(r * 0.45)}"/>`;
  }
  out += `<path class="ih-edge" d="${body}"/>`;
  if (p.kind === "link") {
    out += `<circle class="ih-pin" cx="${f1(a[0])}" cy="${f1(a[1])}" r="${f1(r * 0.42)}"/>`;
    if (p.part === "x2") out += `<circle class="ih-tip" cx="${f1(b[0])}" cy="${f1(b[1])}" r="${f1(r * 1.05)}"/>`;
  }
  return `${out}</g>`;
}

/** The moving pieces; `scope` keeps their clip-path ids apart when several hands are on the page. */
function dynamicArt(pose: (typeof POSES)[Command], lit: boolean, scope: string) {
  const all = pieces(pose);
  const order = (list: Piece[]) => [...list].sort((p, q) => K.depthOf(centroid(p), P) - K.depthOf(centroid(q), P));
  const behind = order(all.filter(behindPalm));
  const front = order(all.filter((p) => !behindPalm(p)));
  const draw = (list: Piece[], tag: string) => list.map((p, i) => pieceSvg(p, `${scope}-${tag}${i}`, lit)).join("");
  return { behind: draw(behind, "b"), front: draw(front, "f") };
}

const SAYS: Record<Command, string> = {
  IDLE: "at rest",
  HAND_GRASP: "the hand closed",
  SIXTH_FINGER_FLEX: "the sixth finger bent",
};

/** The hand as an isometric drawing, posed by the command. */
export function IsoHand({ command }: { command: Command }) {
  const scope = `ih${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const art = useMemo(() => staticArt(), []);
  const behind = useRef<SVGGElement>(null);
  const front = useRef<SVGGElement>(null);
  const current = useRef<number[] | null>(null);

  useEffect(() => {
    const goal = flat(POSES[command]);
    current.current ??= goal.slice();
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let prev = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - prev) / 1000, 0.1);
      prev = now;
      const cur = current.current!;
      let moving = false;
      for (let i = 0; i < cur.length; i++) {
        cur[i] = still ? goal[i] : damp(cur[i], goal[i], 10, dt);
        if (Math.abs(cur[i] - goal[i]) > 1e-3) moving = true;
      }
      const d = dynamicArt(unflat(cur), command === "SIXTH_FINGER_FLEX", scope);
      if (behind.current) behind.current.innerHTML = d.behind;
      if (front.current) front.current.innerHTML = d.front;
      if (moving) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [command, scope]);

  return (
    <svg className="iso-svg iso-hand" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`The hand, ${SAYS[command]}`}>
      <g dangerouslySetInnerHTML={{ __html: art.back }} />
      <g ref={behind} />
      <g dangerouslySetInnerHTML={{ __html: art.palm }} />
      <g dangerouslySetInnerHTML={{ __html: art.housing }} />
      <g ref={front} />
    </svg>
  );
}

type Pose = (typeof POSES)[Command];
const flat = (p: Pose) => [...p.thumb, ...p.fingers.flat(), ...p.sixth];
function unflat(v: number[]): Pose {
  const t = [v[0], v[1], v[2]] as const;
  const fingers = [0, 1, 2, 3].map((i) => [v[3 + i * 3], v[4 + i * 3], v[5 + i * 3]] as const);
  return { thumb: t, fingers, sixth: [v[15], v[16], v[17]] as const };
}
