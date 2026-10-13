import { describe, expect, it } from "vitest";
import { buildChain, fingerPoints, LINKS, PAPER, PEN_X, PX_PER_S, ROW_Y, SECONDS, WINDOW_X1 } from "./chain";

describe("the bench", () => {
  it("draws every part with finite coordinates", () => {
    const art = buildChain();
    expect(art.back.length).toBeGreaterThan(1000);
    expect(art.front.length).toBeGreaterThan(1000);
    expect(`${art.back}${art.front}`).not.toMatch(/NaN|Infinity/);
    expect(art.front.match(/class="lamp"/g)).toHaveLength(3);
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
