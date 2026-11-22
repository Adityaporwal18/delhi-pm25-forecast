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

### Scale

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--type-title` | 28px / 34px | 700 | page title (20px / 26px below 768px) |
| `--type-heading` | 18px / 24px | 600 | panel headings |
| `--type-body` | 15px / 22px | 400 | body, controls |
| `--type-value` | 32px / 36px | 700 | the headline forecast number |
| `--type-caption` | 13px / 18px | 400 | captions, legend, footer |

### Font Stack

System UI stack (no web-font download): `system-ui, -apple-system, "Segoe UI", Roboto,
"Helvetica Neue", Arial, sans-serif`. Numbers use `font-variant-numeric: tabular-nums`.

### Rules

- Values always carry their unit (µg/m³) and times their zone (Delhi time).

## 4. Spacing & Layout

### Base Unit

4px. Scale: 4, 8, 12, 16, 24, 32 (`--space-1` … `--space-6`). Radii: panels 12px, controls
8px, chips 999px.

### Grid

- ≥ 1024px: header; a two-column main area (map `minmax(0, 1fr)`, side panel 400px); footer.
  The map fills the viewport height minus header and footer (at least 520px).
- < 1024px: one column — header, controls, map (55vh, at least 320px), chart, legend, footer.

### Rules

- One scroll container (the page). The map never traps scrolling: wheel zoom is on, and the
  page scrolls around it.

## 5. Components

### Panel
Surface `--ink-900`, 1px `--ink-800` border, 12px radius, inset top highlight
`rgba(255,255,255,0.04)`, shadow `0 10px 30px rgba(0,0,0,0.35)`. States: default only.

### Field (label + native control)
Native `<select>` and `<input type="date">` on `--ink-850`, 1px `--ink-800` border, 8px
radius. States: hover (border `--ink-600`), focus-visible (2px `--focus` ring), disabled
(50% opacity).

### Segmented control (horizon)
Row of buttons; the selected one is filled `--violet-500` with `aria-pressed="true"`. States:
hover (`--ink-800` fill), focus-visible ring, active (`--violet-700`).

### Station marker (map)
Circle filled with the station's category colour (`--ink-600` when blank), 1.5px `--ink-950`
outline. Selected: radius 11 instead of 8, 3px white outline. Hover: tooltip with station name,
forecast and band. Keyboard users choose stations with the station `<select>`.

### Forecast chart card
Recharts: the 80% band as an area (`--band`), the median as a `--violet-300` line starting from
the value measured now, measured values as white dots, faint horizontal CPCB bands behind.
X axis: hours ahead ("now", +6 h … +48 h). States: loading (caption "Loading forecast…"),
empty (station has no forecast: caption), error (message and Retry button).

### Legend
Six swatches with names and µg/m³ ranges, titled "PM2.5-based category (µg/m³)", plus a
one-line note on the 24-hour-average definition.

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

## 7. Accessibility & Accepted Debt

- `lang="en"`, landmarks (header, main, footer), `aria-live="polite"` status line for loading
  and errors, visible focus everywhere, every control labelled.
- Accepted debt: no separate component showcase page (primitives are checked in the real
  page at 375 / 768 / 1280px); no Lighthouse run yet (the audit script needs `uv`, which is
  not installed on this machine).
