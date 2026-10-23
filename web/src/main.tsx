import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter/index.css";
import "@fontsource/eb-garamond/400.css";
import "@fontsource/eb-garamond/400-italic.css";
import App from "./App";
import { DESCRIPTION, TITLE } from "./classic/chapters";
import { Live } from "./Live";
import "./styles.css";

// The chapter-by-chapter page loads on its own, so the main page carries none of its code or styles.
const Classic = lazy(() => import("./classic/Classic").then((m) => ({ default: m.Classic })));

const path = window.location.pathname.replace(/\/+$/, "");
const at = (page: string) => path === `${import.meta.env.BASE_URL}${page}`;

if (at("classic")) {
  document.title = TITLE;
  document.querySelector('meta[name="description"]')?.setAttribute("content", DESCRIPTION);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {at("live") ? (
      <Live />
    ) : at("classic") ? (
      <Suspense fallback={null}>
        <Classic />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
