// The demo's data source as a React hook: one DemoController for the page, its
// messages written into the store, its controls returned to the components.

import { useEffect, useRef } from "react";
import { useDemo } from "../store";
import { DemoController } from "./demoController";
import type { ControlMessage, Mode } from "./types";

export interface DemoStreamControls {
  control: (message: ControlMessage) => void;
  retry: () => void;
  /** Per trial or continuous, without reloading the page. */
  setMode: (mode: Mode) => void;
  /** Decode in this browser even though a server is there. */
  useBrowser: () => void;
  /** Whether there is a server to go back to. */
  hasServer: boolean;
}

function isLoopback(url: string) {
  try {
    return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(url).hostname);
  } catch {
    return false;
  }
}

export function streamSettings(search: string) {
  const params = new URLSearchParams(search);
  const mode: Mode = params.get("mode") === "continuous" ? "continuous" : "trial";
  const speed = Number(params.get("speed")) || 1;
  // "none" builds a site that only decodes in the browser (a static host with no server).
  // A link may point a built site only at "none" or a server on the same machine: the badge
  // vouches for whatever answers, so a link must not swap in someone else's server.
  const link = params.get("server");
  const linkOk = !!link && (import.meta.env.DEV || link === "none" || isLoopback(link));
  const asked = (linkOk ? link : null) || import.meta.env.VITE_SERVER_URL || "http://localhost:8000";
  const serverUrl = asked === "none" ? "" : asked;
  // A model server on the site itself (a path such as /api/decode), used only when there is no
  // streaming server; a link saying server=none turns it off too.
  const decodeUrl = serverUrl || link === "none" ? "" : import.meta.env.VITE_DECODE_URL || "";
  return { mode, speed, serverUrl, decodeUrl };
}

export function useDemoStream(): DemoStreamControls {
  const controller = useRef<DemoController | null>(null);
  useEffect(() => {
    const { applyMessage, setSource, setError } = useDemo.getState();
    const c = new DemoController({
      ...streamSettings(window.location.search),
      onMessage: applyMessage,
      onSource: setSource,
      onError: setError,
    });
    controller.current = c;
    c.start();
    // A hidden tab pauses the demo, and showing it again resumes it if we paused it.
    let pausedForTab = false;
    const onVisibility = () => {
      const paused = useDemo.getState().paused;
      if (document.hidden && !paused) {
        pausedForTab = true;
        c.control({ type: "pause" });
      } else if (!document.hidden && pausedForTab) {
        pausedForTab = false;
        c.control({ type: "resume" });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    const warm = setInterval(() => {
      if (!document.hidden) c.keepWarm();
    }, 10 * 60_000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      clearInterval(warm);
      c.stop();
    };
  }, []);
  return {
    control: (message) => controller.current?.control(message),
    retry: () => controller.current?.retry(),
    setMode: (mode) => {
      const url = new URL(window.location.href);
      if (mode === "trial") url.searchParams.delete("mode");
      else url.searchParams.set("mode", mode);
      window.history.replaceState(null, "", url);
      controller.current?.setMode(mode);
    },
    useBrowser: () => controller.current?.useBrowser(),
    hasServer: (() => {
      const { serverUrl, decodeUrl } = streamSettings(window.location.search);
      return serverUrl !== "" || decodeUrl !== "";
    })(),
  };
}
