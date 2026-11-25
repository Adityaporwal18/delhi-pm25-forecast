import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// Self-hosted fonts, Latin only (about 68 KB): Rozha One for display, IBM Plex Mono for labels,
// Atkinson Hyperlegible for text.
import "@fontsource/rozha-one/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
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
