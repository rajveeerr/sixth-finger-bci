import { describe, expect, it } from "vitest";
import { bend, buildChain, fingerPoints, LIFT, LINKS, PAPER, PARTS, PEN_X, PX_PER_S, ROW_Y, SECONDS, WINDOW_X1 } from "./chain";

describe("the bench", () => {
  it("draws every part with finite coordinates", () => {
    const { layers } = buildChain();
    const svg = layers.map((l) => l.svg).join("");
    expect(svg.length).toBeGreaterThan(2000);
    expect(svg).not.toMatch(/NaN|Infinity/);
    expect(svg.match(/class="lamp"/g)).toHaveLength(3);
    expect(layers.flatMap((l) => l.bend ?? []).join("")).not.toMatch(/NaN|Infinity/);
  });

  it("takes apart into the five named parts, each with a shadow and a hit area", () => {
    const { layers } = buildChain();
    const hits = layers.map((l) => l.svg).join("").match(/data-hit="\d"/g) ?? [];
    PARTS.forEach((part, i) => {
      expect(layers.some((l) => l.kind === "part" && l.part === part.id && (l.svg || l.live))).toBe(true);
      expect(layers.filter((l) => l.kind === "shadow" && l.part === part.id)).toHaveLength(1);
      expect(hits).toContain(`data-hit="${i}"`);
    });
    // The live ink and finger keep their places: ink between the paper and the pen, the finger last.
    const order = layers.map((l) => l.live ?? (l.kind === "part" ? l.part : l.kind));
    expect(order.indexOf("ink-old")).toBeLessThan(order.indexOf("ink-new"));
    expect(order.lastIndexOf("amp")).toBeGreaterThan(order.indexOf("ink-new"));
    expect(order[order.length - 1]).toBe("finger");
  });

  it("keeps a wire's ends on their parts when either one lifts", () => {
    const a: [number, number] = [120, 80];
    const b: [number, number] = [260, 150];
    const [m0, m1, m2, m3, m4, m5] = bend(a, b);
    const map = ([x, y]: [number, number]) => [m0 * x + m2 * y + m4, m1 * x + m3 * y + m5];
    expect(map(a)[0]).toBeCloseTo(a[0]);
    expect(map(a)[1]).toBeCloseTo(a[1] - LIFT);
    expect(map(b)[0]).toBeCloseTo(b[0]);
    expect(map(b)[1]).toBeCloseTo(b[1]);
  });

  it("puts 7.6 s of EEG on the paper and holds the newest 4 s in the frame", () => {
    expect(PEN_X + SECONDS * PX_PER_S).toBeCloseTo(PAPER.x + PAPER.w);
    expect((WINDOW_X1 - PEN_X) / PX_PER_S).toBeCloseTo(4);
    expect(ROW_Y).toHaveLength(7);
    expect(Math.min(...ROW_Y)).toBeGreaterThan(PAPER.y);
    expect(Math.max(...ROW_Y)).toBeLessThan(PAPER.y + PAPER.d);
  });

  it("keeps the finger's links their length as it curls", () => {
    for (const angles of [[0, 0, 0], [0.95, 0.85, 0.65]]) {
      const pts = fingerPoints(angles);
      LINKS.forEach((len, i) => {
        const [a, b] = [pts[i], pts[i + 1]];
        expect(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])).toBeCloseTo(len);
      });
    }
    const open = fingerPoints([0, 0, 0]);
    expect(open[3][0]).toBeCloseTo(open[0][0]); // straight up when open
    expect(fingerPoints([0.95, 0.85, 0.65])[3][0]).toBeGreaterThan(open[3][0]); // curled toward +x
  });
});
