import { afterEach, describe, expect, it, vi } from "vitest";
import { streamSettings } from "./useDemoStream";

describe("streamSettings on a built site", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("takes no server from a link to another machine", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_SERVER_URL", "none");
    expect(streamSettings("?server=https://example.org").serverUrl).toBe("");
  });

  it("takes a server on this machine, or none, from a link", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_SERVER_URL", "none");
    expect(streamSettings("?server=http://127.0.0.1:9").serverUrl).toBe("http://127.0.0.1:9");
    expect(streamSettings("?server=none").serverUrl).toBe("");
  });

  it("uses the built-in server when the link names none", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_SERVER_URL", "https://server.example");
    expect(streamSettings("").serverUrl).toBe("https://server.example");
  });
});
