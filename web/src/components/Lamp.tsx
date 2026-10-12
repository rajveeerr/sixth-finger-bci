import { useMemo } from "react";
import * as K from "../explain/iso/kit";

// One indicator lamp in the bench's finish: a bezel on a small base, its lens lit in the
// class colour when this is the decision.

const W = 96;
const H = 66;
const P = K.fitProjection([...K.boxCorners({ x: 0, y: 0, w: 40, d: 40, r: 0 }, 0, 4), [20, 20, 12]], W, H, { pad: 4, azimuth: 45 });

export function Lamp({ kind, on }: { kind: string; on: boolean }) {
  const art = useMemo(() => {
    const base: K.Plan = { x: 0, y: 0, w: 40, d: 40, r: 5 };
    return [
      K.solidSvg(K.slabOf(base, 0, 4, P, 6, 0.6), { tone: "mid", halo: true }),
      K.dotsSvg(K.corners(base, 5).map(([x, y]) => K.iso([x, y, 4], P)), { size: 0.9, tone: "mid" }),
      K.solidSvg(K.cylinder(20, 20, 14, 4, 6, P, 48, 0.8), { tone: "hi" }),
      K.lineSvg(K.knurl(20, 20, 14, 4, 10, 48, P, 1), { tone: "faint" }),
    ].join("");
  }, []);
  const lens = useMemo(() => K.planOutline({ x: 9, y: 9, w: 22, d: 22, r: 11 }, 10, P), []);
  const glint = useMemo(() => K.planOutline({ x: 13, y: 13, w: 6, d: 6, r: 3 }, 10.2, P), []);
  return (
    <svg className="iso-svg lamp-svg" viewBox={`0 0 ${W} ${H}`} aria-hidden="true" data-kind={kind} data-on={on ? "" : undefined}>
      <g dangerouslySetInnerHTML={{ __html: art }} />
      <path className="lamp-lens" d={lens} />
      <path className="lamp-glint" d={glint} />
    </svg>
  );
}
