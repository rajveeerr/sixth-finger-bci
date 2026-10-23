import { describe, expect, it } from "vitest";
import { FILES, fileSize, inWords, READ_TITLE } from "./siteDocs";

describe("the documents' links", () => {
  it("give each size the way a download link does", () => {
    expect(fileSize(283_425)).toBe("0.3 MB");
    expect(fileSize(1_907_681)).toBe("1.9 MB");
    expect(fileSize(41_200)).toBe("41 KB");
  });

  it("name what can be read, in order", () => {
    expect(inWords(["paper"])).toBe("the paper");
    expect(inWords(["paper", "slides", "slides"])).toBe("the paper and the slides");
    expect(inWords(["paper", "slides", "report"])).toBe("the paper, the slides and the report");
    expect(READ_TITLE).toBe(`Read ${inWords(FILES.map((f) => f.doc))}`);
  });

  it("link only files the site serves, each under 5 MB, with the paper marked a draft", () => {
    for (const f of FILES) {
      expect(f.href).toBe(`/docs/${f.file}`);
      expect(f.bytes).toBeLessThan(5_000_000);
    }
    expect(FILES.find((f) => f.doc === "paper")?.tag).toBe("Preprint draft");
  });
});
