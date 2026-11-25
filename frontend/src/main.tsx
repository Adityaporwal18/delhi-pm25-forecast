import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// Self-hosted fonts, Latin only (about 57 KB): Bricolage Grotesque for display, Atkinson Hyperlegible for text.
import "@fontsource/bricolage-grotesque/latin-700.css";
import "@fontsource/atkinson-hyperlegible/latin-400.css";
import "@fontsource/atkinson-hyperlegible/latin-700.css";
import "./styles.css";
import "./phone.css";

if (import.meta.env.DEV) {
  void import("react-grab");
  void import("react-scan");
}

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root element");
}
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
