import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectServer, streamUrl, type CloseReason } from "./connection";

class FakeSocket {
  sent: string[] = [];
  closed = false;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  constructor(public url: string) {}
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  receive(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }
}

function open() {
  let socket!: FakeSocket;
  const closes: (CloseReason | number | undefined)[][] = [];
  const conn = connectServer(
    "http://localhost:8000",
    "trial",
    { onMessage: () => {}, onClose: (reason, code) => closes.push([reason, code]) },
    { socket: (url) => (socket = new FakeSocket(url)) as unknown as WebSocket },
  );
  return { socket, closes, conn };
}

describe("connectServer", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("derives ws or wss from the server's URL", () => {
    expect(streamUrl("https://x.hf.space", "trial")).toMatch(/^wss:\/\/x\.hf\.space\/ws\/stream\?mode=trial/);
    expect(streamUrl("http://localhost:8000", "continuous", 8)).toBe(
      "ws://localhost:8000/ws/stream?mode=continuous&speed=8",
    );
  });

  it("fails when no hello arrives within 2 s", () => {
    const { closes } = open();
    vi.advanceTimersByTime(2001);
    expect(closes).toEqual([["timeout", undefined]]);
  });

  it.each([1008, 1013])("treats close code %i as a rejected server", (code) => {
    const { socket, closes } = open();
    socket.receive({ type: "hello" });
    socket.onclose?.({ code } as CloseEvent);
    expect(closes).toEqual([["rejected", code]]);
  });

  it("drops a server that goes silent for 5 s", () => {
    const { socket, closes } = open();
    socket.receive({ type: "hello" });
    vi.advanceTimersByTime(4000);
    socket.receive({ type: "eeg" });
    vi.advanceTimersByTime(4000);
    expect(closes).toEqual([]);
    vi.advanceTimersByTime(1001);
    expect(closes).toEqual([["timeout", undefined]]);
  });

  it("keeps a paused stream with its heartbeats, and rests the watchdog while paused", () => {
    const { socket, closes, conn } = open();
    socket.receive({ type: "hello" });
    conn.send({ type: "pause" });
    vi.advanceTimersByTime(10_000); // silent: the watchdog rests while paused
    socket.receive({ type: "status", paused: true, speed: 1 });
    vi.advanceTimersByTime(10_000); // a message while paused does not wake it either
    expect(closes).toEqual([]);
    for (let i = 0; i < 6; i++) {
      vi.advanceTimersByTime(2000);
      socket.receive({ type: "status", paused: true, speed: 1 }); // heartbeats
    }
    expect(closes).toEqual([]);
    conn.send({ type: "resume" });
    vi.advanceTimersByTime(5001);
    expect(closes).toEqual([["timeout", undefined]]);
    expect(socket.sent.map((s) => JSON.parse(s).type)).toEqual(["pause", "resume"]);
  });

  it("reports nothing after the caller closes it", () => {
    const { socket, closes, conn } = open();
    socket.receive({ type: "hello" });
    conn.close();
    vi.advanceTimersByTime(10_000);
    socket.onclose?.({ code: 1000 } as CloseEvent);
    expect(closes).toEqual([]);
  });
});
