import { expect, it } from "vitest";
import html from "../index.html?raw";

function tag(attribute: "name" | "property", key: string): string | undefined {
  return new RegExp(`<meta ${attribute}="${key}" content="([^"]*)"`).exec(html)?.[1];
}

it("describes the live forecast first and the held-out 2025 evaluation second, never as AQI", () => {
  const description = tag("name", "description") ?? "";
  expect([description.startsWith("Live 48-hour PM2.5"), description.includes("held-out 2025"), html.includes("AQI")]).toEqual([
    true,
    true,
    false,
  ]);
});

it("gives link previews the same title and description as the page", () => {
  const title = /<title>([^<]*)<\/title>/.exec(html)?.[1];
  expect([tag("property", "og:title"), tag("property", "og:description")]).toEqual([title, tag("name", "description")]);
});
