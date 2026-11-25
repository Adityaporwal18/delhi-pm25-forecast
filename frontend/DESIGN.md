# Delhi PM2.5 Forecast — Design System

Design read: a public-interest data dashboard for recruiters and interviewers. Serious,
trustworthy and data-dense; honest about uncertainty; accessible. The six CPCB category colours
carry the meaning, so the interface around them stays quiet. Layer A: `taste-skill`
(operational UI). Layer B: `sentry` (dark, data-dense dashboard): its aubergine surfaces, violet
interaction colour and pink focus ring are kept; its lime accent is dropped because it would
collide with CPCB's "Satisfactory" green.

## 1. Atmosphere & Identity

- Night-time dashboard: deep aubergine page with a soft violet glow at the top-left (layered
  radial gradient), raised panels with a 1px border, a faint top highlight and a soft shadow.
- The map is the hero; the selected station's 48-hour chart is the second focus. Base map:
  OpenStreetMap's free tiles (attribution kept), inverted by a CSS filter into a dark map;
  CARTO's dark tiles were tried first but now need an API key, which breaks "free tools only".
- Copy says "PM2.5", "µg/m³" and "PM2.5-based category". Never "AQI".
- Every screen states that this is a replay of 2025, not a live forecast.

## 2. Color

### Palette

| Token | Value | Source | Use |
|---|---|---|---|
| `--ink-950` | `#150f23` | sentry | page background |
| `--ink-900` | `#1f1633` | sentry | panels |
| `--ink-850` | `#261c3d` | derived (between 900 and 800) | raised controls, chart card |
| `--ink-800` | `#362d59` | sentry | borders, dividers, grid lines |
| `--ink-600` | `#79628c` | sentry | muted marks, markers without data |
| `--violet-500` | `#6a5fc1` | sentry | interactive: selected segment, links |
| `--violet-300` | `#a99cf0` | derived (lighter step of 500) | forecast median line |
| `--violet-700` | `#422082` | sentry | active / pressed |
| `--focus` | `#fa7faa` | sentry | focus-visible ring |
| `--text` | `#ffffff` | sentry | primary text |
| `--text-muted` | `#e5e7eb` | sentry | secondary text |
| `--text-subtle` | `#b9b1cc` | derived (muted on ink) | captions, footnotes |
| `--band` | `rgba(106, 95, 193, 0.35)` | violet-500 at 35% | 80% uncertainty band |
| `--measured` | `#ffffff` | text | measured dots |

Data colours (CPCB PM2.5 bands, served by `/api/meta`): Good `#00b050`, Satisfactory `#92d050`,
Moderate `#ffff00`, Poor `#ff9900`, Very Poor `#ff0000`, Severe `#c00000`.

### Rules

- Data colours appear only on data (markers, legend swatches, category chips). UI chrome
  never uses them.
- Colour is never the only cue: every coloured value also shows its number and category name.
- Text contrast meets WCAG AA on `--ink-900` and `--ink-950`.

## 3. Typography

### Faces (self-hosted, Latin subset only, about 57 KB in total, `font-display: swap`)

- Display: **Bricolage Grotesque 700**. Headline, panel headings, the forecast number, and the
  accuracy figures: a grotesque with character in its numerals.
- Text: **Atkinson Hyperlegible 400 and 700** (designed by the Braille Institute for legibility:
  distinct 0/O, 1/l/I). Everything else. Its slashed zero is intended.

### Scale (about 1.25 from the 15px body)

| Token | Size / line height | Face | Use |
|---|---|---|---|
| focal | 64px / 0.95, -0.035em | display | the station's forecast number (52px below 768px) |
| title | 30px / 1.1 | display | page title (22px below 768px) |
| heading | 19px / 1.25 | display | panel headings, station name |
| fact | 19px | display | figures inside the accuracy panel |
| lead | 17px / 1.45 | text | introductory sentences |
| body | 15px / 1.5 | text | status line, body |
| small | 13-14px / 1.45 | text | captions, caveats, legend |
| overline | 11px, 700, uppercase, 0.09em | text | labels; never applied to units |

### Rules

- Numbers on screen are rounded to what the data supports: whole µg/m³ for forecasts and bands.
- Units are never upper-cased: an upper-case micro sign reads as M (milligrams).

## 4. Spacing & Layout

### Base Unit

4px. Scale: 4, 8, 12, 16, 24, 32 (`--space-1` … `--space-6`). Radii: panels 12px, controls
8px, chips and tags 999px.

### Grid

- ≥ 1200px: header; a full-width **status line** (the forecast's time, stations reporting, last
  update; or what the replay shows); then three columns: map `minmax(0, 1fr)` | station 336px |
  context 340px. The map fills the window below the status line, with the colour key laid over
  its bottom-left corner.
- 768–1199px: one column (status line, map, station, context); the time bar and the legend
  stay laid over the map, which is wide enough for them.
- ≤ 767px (phones, design stage 5, `phone.css`): one stacked column and **nothing over the
  map**: status line ("N of 37 stations") → time bar (its own row above the map, the scrubber
  on a full-width line) → map (`min(62vh, 480px)`, at least 340px) → legend ("This is not the
  AQI", directly under the map) → station → accuracy (the held-out-2025 paragraph and the
  heavy-smog caveat). Every caveat stays in the normal scroll; none is collapsed. Checked at
  360×800: no sideways scrolling, all 37 dots inside the map.
- Touch screens (`pointer: coarse`): a 44px play button, a 24px scrubber thumb on a 32px-tall
  track, and the numbers under it widened to match.

### Rules

- **The fold rule:** on desktop (checked at 1366×768, the commonest laptop screen in India),
  these stay visible without scrolling: the status line's "N of 37 stations", the "not a
  measurement of this forecast" paragraph, the heavy-smog numbers, and "This is not the AQI".
- One scroll container (the page).

## 5. Components

Three surface weights, so that the station panel leads:
- **Primary** (the station's forecast card): lighter top gradient, `--ink-700` border, 24px
  padding, deep shadow. One per view.
- **Panel** (accuracy, controls): `--ink-900` with a 1px border.
- **Quiet** (status line): no box; text only.

### Focal value
The forecast number in the focal style, the unit (µg/m³) at 17px, and a **category chip** (the
CPCB colour swatch and its name), then when it is for and the 80% band.

### Status line
Full width under the header: a violet **tag** ("Live", "Replay of 2025"), then facts separated by
middle dots. A stale forecast adds a Warning below it.

### Map legend (overlay)
232px, bottom-left of the map, near-opaque `--ink-950`: overline title with the unit in normal
case, six swatches with ranges, and the "This is not the AQI" caption. On phones it leaves the
map and sits directly under it, full width, separated by a 1px `--ink-800` rule.


### Panel
Surface `--ink-900`, 1px `--ink-800` border, 12px radius, inset top highlight
`rgba(255,255,255,0.04)`, shadow `0 10px 30px rgba(0,0,0,0.35)`. States: default only.

### Field (label + native control)
Native `<select>` and `<input type="date">` on `--ink-850`, 1px `--ink-800` border, 8px
radius. States: hover (border `--ink-600`), focus-visible (2px `--focus` ring), disabled
(50% opacity).

### Segmented control (Live / Accuracy)
Row of buttons; the selected one is filled `--violet-500` with `aria-pressed="true"`. States:
hover (`--ink-800` fill), focus-visible ring, active (`--violet-700`).

### Time bar (map overlay)
Over the top of the map (12px in, clear of the zoom buttons), near-opaque `--ink-950`, and the
only way to choose the map's hour (the side column no longer has hour buttons). Left to right:
- a 36px round `--violet-500` play/pause button (`aria-label` "Play through the forecast hours" /
  "Pause");
- the hour now shown, always visible: "+24 h" (display face, 22px) over its Delhi time
  ("Mon 15 Dec 2025, 20:00"), at a fixed 158px width so the scrubber never shifts;
- a native range scrubber with one stop per forecast hour (6 … 48; horizon 0 is a measurement,
  so it is left out), numbered underneath, the current number in bold. `aria-valuetext` reads
  "24 hours ahead, Mon 15 Dec 2025, 20:00".
Playing shows each hour for 1s, starts from +6 h when pressed at the end, stops at +48 h (no
loop), and waits for the shown hour's data, so the label never runs ahead of the dots. Dragging
the scrubber or hiding the view pauses it. The replay fetches all 8 hours of a forecast at once
(about 7 KB compressed) so stepping never waits on the network. The map's fit leaves 80px at the
top so no station sits under the bar; the replay's loading notice sits below it. The scrubber
needs at least 120px, so the bar stays on one row down to the 1200px desktop layout (checked:
59px tall at 1200 and 1366 wide, no station under it). On phones the bar is a normal row above
the map, not laid over it.

### Station marker (map)
Circle filled with the station's category colour (`--ink-600` when blank), 1.5px `--ink-950`
outline. Size encodes the forecast: area ∝ µg/m³ (radius = 13 × √(value / 250)), clamped to
4–21px (`markers.ts`); bigger dots are drawn first so small ones stay on top. Above 250 (Severe):
a 2px `#ff5a5a` ring that pulses outward (1.8s; still under reduced motion); the three highest
Severe stations also get their number written beside the dot. Selected: same size (size means
value), a separate 2.5px white ring 4px outside the dot, the station's short name beside it, and
drawn last. Labels of stations in the eastern third of the map go on the left of the dot, so
Anand Vihar's name is not cut off by the map's edge on a phone. No current reading: dashed `--text-subtle` outline. Hover: tooltip with station name,
forecast and band. Keyboard users choose stations with the station `<select>`. No interpolated
field between stations (only a labelled mockup exists: `docs/design/stage2-interpolation-mockup.png`).

### 3D columns (prototyped in design stage 4, not built)
Brief: deck.gl extruded columns over Leaflet, behind a toggle that is off by default and loads
lazily; skip it if it confuses more than it shows. Findings (25 Nov 2026):
- Leaflet has no tilt, so deck.gl drawn over it looks straight down, and columns look like the
  dots we already have. Showing height means replacing the map with deck.gl's own tilted view
  and its own basemap tiles.
- That prototype (deck.gl 9.4.2: core, ColumnLayer, TileLayer, TextLayer) adds a 1,021 KB
  script, 234 KB at maximum brotli and 284 KB at gzip, about as much again as the whole site's
  JavaScript. It also needs WebGL, which is heavy on a mid-range phone's battery.
- On the 14 Dec 2025 Severe night (`docs/design/stage4-3d-prototype.png`):
  - the clustered central stations hide one another, and the base of a column, which shows
    where its station is, is hidden behind the columns in front;
  - perspective makes equal values look different heights, so the highest value (466) does
    not look tallest;
  - floating labels are hard to tie to their columns.
- Verdict: it confuses more than it shows. The 2D map (area-scaled dots, Severe ring, top
  three numbered) stays. The prototype lived in a scratch folder; nothing was added to the site.

### Forecast chart card
Recharts: the 80% band as an area (`--band`), the median as a `--violet-300` line starting from
the value measured now, measured values as white dots, faint horizontal CPCB bands behind, and
a dashed white line (70% opacity) at the hour the map shows, which moves with playback.
X axis: hours ahead ("now", +6 h … +48 h). States: loading (caption "Loading forecast…"),
empty (station has no forecast: caption), error (message and Retry button).

### Legend
Six swatches with names and µg/m³ ranges, titled "PM2.5-based category (µg/m³)", a size key
(outline circles for 50, 150, 300 with a note on the ring and the dashed outline), plus a
one-line note on the 24-hour-average definition ending "This is not the AQI."

### Notice
A pill-shaped badge "Replay of 2025, not a live forecast" in the header.

### Mode switch (Live / Accuracy)
The segmented control, two options, at the right of the header ("Live", "Accuracy (2025 replay)"),
600 weight, 16px side padding. Live is the default; the choice is kept in the URL (#live, #accuracy).

### Accuracy panel
A Panel with the evaluation model's held-out 2025 numbers (from `/api/accuracy`): the 48-hour
average error with the two baselines for comparison, the band's coverage, and the heavy-smog caveat
as a Warning. Titled "Expected accuracy" in the live view (with its source stated: held-out 2025
testing, not a measurement of the live forecast) and "Accuracy in the held-out 2025 test year" in
the replay. Never shown without the caveat.

### Freshness panel (live)
"Forecast from <Delhi time>, with readings from N of 37 stations", then "Last updated … (N hours
ago)" as a caption. Older than 12 hours: a Warning that the last good forecast is shown.

### Warning
Body text with a 3px `--focus` left border and 12px padding: the reader must not miss it.

### Footer
Credits (from `/api/meta`) and the replay note, `--type-caption`, `--text-subtle`.

## 6. Motion & Interaction

### Timing

- 120ms ease-out colour and border transitions on hover/focus of controls only.
- No chart or map animation: values change instantly when the time or horizon changes, so
  what is shown always matches the controls. `prefers-reduced-motion` removes the transitions.
- Playback (the time bar) steps through the forecast hours, one per second; it never tweens
  between them, because an in-between frame would show values that were never forecast. It only
  runs when the reader presses Play, so it is not affected by `prefers-reduced-motion`.
- One exception: the Severe ring's pulse (1.8s ease-out, looping), which carries no value.
  `prefers-reduced-motion` stops it and leaves a still ring.

## 7. Accessibility & Accepted Debt

- `lang="en"`, landmarks (header, main, footer), `aria-live="polite"` status line for loading
  and errors, visible focus everywhere, every control labelled.
- Accepted debt: no separate component showcase page (primitives are checked in the real
  page at 375 / 768 / 1280px); no Lighthouse run yet (the audit script needs `uv`, which is
  not installed on this machine).
