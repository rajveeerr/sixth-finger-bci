import { describe, expect, it } from "vitest";
import { data } from "../data";
import { buildModel, CHANNELS, SFREQ, STAGES, WINDOW_S } from "./model";

describe("the model drawing", () => {
  it("draws every station with finite coordinates and three lamps", () => {
    const art = buildModel();
    const all = [art.input, ...art.steps].join("");
    expect(all).not.toMatch(/NaN|Infinity/);
    expect(art.input.match(/M/g)!.length).toBeGreaterThan(CHANNELS);
    expect(art.steps[3].match(/class="lamp"/g)).toHaveLength(3);
  });

  it("labels the sizes of the exported model", () => {
    const { rhythms, sensors, combine, decide } = STAGES;
    expect(rhythms.learned + sensors.learned + combine.learned + decide.learned).toBe(data.demo.parameters);
    expect(rhythms.filters * sensors.perFilter).toBe(sensors.outputs);
    // Each even-length kernel, padded by half its length, adds one reading before its average.
    const afterFirst = Math.floor((WINDOW_S * SFREQ + 1) / sensors.pool);
    expect(Math.floor((afterFirst + 1) / combine.pool)).toBe(combine.steps);
  });
});
