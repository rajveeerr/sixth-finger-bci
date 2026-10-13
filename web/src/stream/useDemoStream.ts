// The demo's data source as a React hook: one DemoController for the page, its
// messages written into the store, its controls returned to the components.

import { useEffect, useRef } from "react";
import { useDemo } from "../store";
import { DemoController } from "./demoController";
import type { ControlMessage, Mode } from "./types";

export interface DemoStreamControls {
  control: (message: ControlMessage) => void;
  retry: () => void;
  /** Whether there is a server to go back to. */
  hasServer: boolean;
}

export function streamSettings(search: string) {
  const params = new URLSearchParams(search);
  const mode: Mode = params.get("mode") === "continuous" ? "continuous" : "trial";
  const speed = Number(params.get("speed")) || 1;
  // "none" builds a site that only decodes in the browser (a static host with no server).
  const asked = params.get("server") || import.meta.env.VITE_SERVER_URL || "http://localhost:8000";
  const serverUrl = asked === "none" ? "" : asked;
  return { mode, speed, serverUrl };
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
    return () => c.stop();
  }, []);
  return {
    control: (message) => controller.current?.control(message),
    retry: () => controller.current?.retry(),
    hasServer: streamSettings(window.location.search).serverUrl !== "",
  };
}
