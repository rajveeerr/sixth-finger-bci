import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter/index.css";
import "@fontsource/eb-garamond/400.css";
import "@fontsource/eb-garamond/400-italic.css";
import App from "./App";
import { Live } from "./Live";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname.replace(/\/+$/, "") === `${import.meta.env.BASE_URL}live` ? <Live /> : <App />}
  </StrictMode>,
);
