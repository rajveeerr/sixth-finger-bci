import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/bundle.json";
import { applyPreprocessing, parseBundle, windowOf, type PreprocessOp } from "./bundle";
import { readDemoBundle } from "./demoBundle.testutil";

describe("bundle", () => {
  it("reads the trials as the Python Bundle does", () => {
    const bundle = readDemoBundle();
    expect(bundle.manifest.trials.length).toBe(fixture.n_trials);
    const rows = bundle.trial(0);
    expect([rows.length, rows[0].length]).toEqual(fixture.trial0_shape);
    fixture.trial0_head.forEach((head, c) =>
      head.forEach((v, i) => expect(rows[c][i]).toBeCloseTo(v, 3)),
    );
  });

  it("refuses a trials file of the wrong size", () => {
    const bundle = readDemoBundle();
    expect(() => parseBundle("/demo", bundle.manifest, new ArrayBuffer(10))).toThrow(/manifest says/);
  });

  it("cuts channel-major windows", () => {
    const rows = [Float32Array.from([1, 2, 3, 4]), Float32Array.from([5, 6, 7, 8])];
    expect(Array.from(windowOf(rows, 1, 3))).toEqual([2, 3, 6, 7]);
  });
});

describe("applyPreprocessing", () => {
  it("matches server/app/bundle.py on every operation", () => {
    const nCh = fixture.window.length;
    const nT = fixture.window[0].length;
    const x = Float32Array.from(fixture.window.flat());
    const out = applyPreprocessing(x, nCh, nT, fixture.ops as PreprocessOp[]);
    fixture.preprocessed.flat().forEach((v, i) => expect(out[i]).toBeCloseTo(v, 4));
  });
});
