# Delhi PM2.5 Forecast — Design System

Design read: a public-interest data page, read like the weather page of a city newspaper.
Serious, honest about uncertainty, accessible, quick on a mid-range phone. The six CPCB category
colours are the only loud colours on the page, because they carry the meaning; everything around
them is paper, ink and hairline rules.

References (redesign of 26 Nov 2026, after the owner found the dark violet version "AI
generated"): Layer A `redesign-skill` (audit-first upgrade of existing UI); Layer B `wired`
(broadsheet density, square corners, hairline rules, mono kickers, one ink-blue accent). Purple,
glows, gradients, pills and drop shadows are removed on purpose.

## 1. Atmosphere & Identity

- **Newsprint, not a dashboard.** A warm paper page (`--paper`, with a faint printed grain), ink
  type, hairline rules between columns instead of cards, square corners, a heavy double rule under
  the masthead, and an inverted ink footer, the only dark region.
- **The map is the hero.** Nothing is laid over it: the time bar sits above it and the colour key
  below it, so every station stays visible. Base map: OpenStreetMap's free tiles in warm
  greyscale, so the category colours read first.
- **A Delhi signature:** the masthead and the big numbers are set in Rozha One, a display face
  that Indian Type Foundry designed for Hindi newspaper headlines.
- Copy says "PM2.5", "µg/m³" and "PM2.5-based category". Never "AQI".

## 2. Color

### Palette

- `--paper` `#f4f0e6`: page (warm newsprint; a hazy-sky tone, not pure white).
- `--paper-hi` `#fbf9f3`: the station card, inputs, map labels.
- `--paper-lo` `#e9e3d5`: sunken wells (heavy-smog note, map loading background).
- `--ink` `#1c1a16`: text, 2px rules, buttons, dot outlines, the selected-station ring.
- `--ink-2` `#4a453d`: secondary text (8.4:1 on paper).
- `--ink-3` `#6a6359`: captions and footnotes (5.2:1 on paper).
- `--rule` `#d5cdbd`: hairline dividers and chart grid.
- `--accent` `#0b5cad`: the single interactive accent (5.9:1 on paper). Focus ring, links,
  the scrubber, the chart's map-hour line, the hovered 3D column. Never used on data.
- `--smog` `#8e1b12`: the heavy-smog note's rule. Kin to the Severe maroon, and used only there.
- `--severe-ring` `#d40d12`: the pulsing ring around stations above 250 µg/m³.
- `--band`: ink at 13%, the 80% uncertainty band.

Data colours (CPCB PM2.5 bands, served by `/api/meta`): Good `#00b050`, Satisfactory `#92d050`,
Moderate `#ffff00`, Poor `#ff9900`, Very Poor `#ff0000`, Severe `#c00000`.

### Rules

- Data colours appear only on data (dots, columns, legend swatches, category chips).
- Every data colour sits inside a 1px ink outline: yellow and light green are otherwise lost on
  paper.
- Colour is never the only cue: every coloured value also shows its number and category name.
- One gray family (warm). No gradients and no shadows; depth comes from rules and the paper tones.

## 3. Typography

### Faces (self-hosted, Latin subset only, about 68 KB in total, `font-display: swap`)

- Display: **Rozha One 400** (18 KB). The masthead title, station name, forecast number, hour
  label and accuracy figures. Shouts, never reads.
- Labels: **IBM Plex Mono 500** (15 KB). Kickers, tags, field labels and timestamps, always
  uppercase with 0.08em tracking; tick numbers stay as they are.
- Text: **Atkinson Hyperlegible 400 and 700** (35 KB). Everything people read.

### Scale

- title: 36px / 0.95, −0.01em, display (28px on phones)
- focal: 76px / 0.9, display (60px on phones)
- headline: 24px / 1.1, display (station name)
- figure: 26px / 1, display (accuracy figures, inline at the start of their sentence; the hour label)
- body: 15px / 1.5, text
- small: 13px / 1.45, text (captions, caveats, legend)
- label: 11.5px / 1.3, mono, uppercase, 0.08em

### Rules

- Units are never upper-cased (an upper-case micro sign reads as M) and never sit in mono caps.
- Numbers are rounded to what the data supports: whole µg/m³ for forecasts and bands.
- Tabular figures for every number that changes in place (hour label, ticks, ranges).
- `text-wrap: pretty` on paragraphs; `balance` on headings.

## 4. Spacing & Layout

### Base

4px unit; scale 4, 8, 12, 16, 24, 32 (`--space-1` … `--space-6`). Radius 0 everywhere, except
the play button and the map dots (circles).

### Grid

- Page: at most 1440px wide, centred, 24px side padding (12px on phones).
- ≥ 1200px: masthead; a full-width status line; then three columns separated by hairline rules:
  map `minmax(0, 1fr)` | station 336px | context 340px.
- The map column is one framed block: time bar → colour key → map (on phones: time bar → map → key). It is sticky and sized to
  the window, so the legend's caveat stays in view.
- 768–1199px: one column (status, map block, station, context).
- ≤ 767px (phones, `phone.css`): the same single column with phone sizes (below).

### The fold rule

On desktop (checked at a 1366×657 viewport, a 1366×768 laptop), these stay visible without
scrolling: the status line's "N of 37 stations", the "not a measurement of this forecast"
paragraph, the heavy-smog numbers, and "This is not the AQI". On phones they stay in the normal
scroll, never collapsed.

## 5. Components

- **Masthead:** a mono kicker ("Delhi · hourly PM2.5 · 37 CPCB monitoring stations"), the title
  in display, then a 3px + 1px ink double rule across the page. The view tabs sit at its right.
- **View tabs** ("Live", "Accuracy (2025 replay)"): text buttons in mono caps. The current one has
  a 3px ink underline and ink text; the others are `--ink-3`, and hover to ink. `aria-pressed`
  marks the current tab.
- **Status line:** a square ink tag ("LIVE", "REPLAY OF 2025") in paper mono caps, then facts
  separated by middle dots. A stale forecast adds a Warning below it.
- **Column:** no card. A hairline rule on the left, 24px inside. A mono kicker heads each
  column.
- **Station card (primary):** `--paper-hi`, a 1px rule border and a 4px ink top rule; the one
  raised surface on the page.
- **Focal value:** the forecast number (focal), the unit at 18px in text, and a category chip:
  a square swatch with an ink outline and the category name. Then when it is for, and the 80%
  band.
- **Field:** mono label above a native `<select>` or `<input type="date">` on `--paper-hi`, a 1px
  ink border, square. Hover: 2px inner ink; focus-visible: 2px accent ring.
- **Button:** square, 2px ink border, paper fill; hover inverts (ink fill, paper text); active
  nudges 1px down. Disabled: 45% opacity.
- **Time bar** (above the map, part of the map block):
  - Left to right: a 38px round ink play/pause button (accent on hover); the hour now shown
    ("+24 h" in figure size over its Delhi time, fixed 160px, so nothing shifts); a native range
    scrubber with one stop per forecast hour (6 … 48).
  - Horizon 0 is a measurement, so it is left out.
  - The scrubber: an ink 2px track, the passed part in accent, a round accent thumb with a paper
    ring, numbers underneath with the current one in ink bold.
  - Playing shows each hour for 1s, starts from +6 h when pressed at the end, stops at +48 h, and
    waits for the shown hour's data. Dragging pauses it.
  - The replay fetches all 8 hours of a forecast at once.
- **Map (2D):**
  - Dots filled with the category colour (`--paper-lo` when blank) and a 1.5px ink outline.
  - Area ∝ forecast: radius = 13·√(value/250), clamped to 4–21px; bigger dots drawn first.
  - Above 250: a 2px `--severe-ring` ring that pulses outward (still under reduced motion), and
    the three highest Severe stations numbered.
  - Selected: same size, a 2.5px ink ring 4px outside the dot, the short name beside it in a
    `--paper-hi` label. Labels in the map's eastern third go on the left of the dot.
  - No current reading: a dashed ink outline.
  - No interpolated field between stations (the labelled mockup in `docs/design/` stays a
    mockup).
- **Map (3D, optional):**
  - Switched on with the "3D" segment in the legend strip. It loads deck.gl only then (a separate
    file, about 0.23 MB with brotli); the page never loads it otherwise.
  - Base map: the same OpenStreetMap tiles in warm greyscale, at a 45° tilt.
  - Each station: a flat ground disc in its category colour with an ink outline, so its place
    stays visible, and a column whose height is proportional to the forecast (40 m per
    µg/m³). Columns are 9px wide and discs 12px, in screen pixels, so they read at any zoom.
    No transitions between hours.
  - The camera fits every station with headroom above for tall columns, tilts 45° and turns
    −12°.
  - The selected station gets an ink ring on the ground and a label with its name and value; the
    three highest Severe values are labelled.
  - Hover shows a tooltip with the value and band; a click selects the station. "Reset view"
    returns the camera.
  - If WebGL is unavailable, a message says so and 2D stays.
- **Legend strip** (between the time bar and the map; below the map on phones):
  - A mono kicker "PM2.5-based category (µg/m³, hourly)".
  - Six equal segments, each a colour bar with an ink outline, the category name, and its range.
  - Then a row: the encoding key (2D: outline circles for 50, 150, 300 with "dot area ∝
    forecast · red ring: above 250 · dashed: no current reading"; 3D: "column height ∝
    forecast"), the caveat "CPCB defines these bands on 24-hour averages; here they colour hourly
    forecasts. This is not the AQI.", and the 2D/3D switch.
- **Forecast chart:**
  - Recharts. The 80% band as an area (`--band`); the median as a 2.5px ink line with dots,
    starting from the value measured now; measured values as hollow circles (paper fill, ink
    stroke).
  - Faint CPCB bands behind; a dashed accent line at the hour the map shows; grid in `--rule`.
  - X axis: "now", +6 h … +48 h.
- **Accuracy column:** kicker title, the source sentence (held-out 2025 testing, not a measurement
  of the live forecast), the figures in display size, then the heavy-smog Warning. Never shown
  without the caveat.
- **Warning:** `--paper-lo` well with a 4px `--smog` left rule; ink text.
- **Footer:** the inverted ink band at the bottom: paper text, credits and the replay note.

## 6. Motion & Interaction

- 150ms colour/background transitions on hover and focus of controls only.
- No chart or map animation: values change instantly when the hour or horizon changes, so what is
  shown always matches the controls. Playback steps through the forecast hours and never tweens
  between them (an in-between frame would show values never forecast).
- One exception: the Severe ring's pulse (1.8s ease-out, looping), which carries no value.
  `prefers-reduced-motion` stops it and removes the transitions.

## 7. Accessibility & Accepted Debt

- `lang="en"`, landmarks (header, main, footer), an `aria-live="polite"` status line for loading
  and errors, a 2px accent focus ring everywhere, every control labelled.
- Touch screens (`pointer: coarse`): a 44px play button, a 24px scrubber thumb.
- The 3D view is an extra, never the only way to read a value. The 2D map, the station chart and
  the station list carry everything.
- Accepted debt: no separate component showcase page (primitives are checked in the real page at
  360, 768, 1200 and 1366px); no Lighthouse run yet (the audit script needs `uv`, which is not
  installed on this machine).
