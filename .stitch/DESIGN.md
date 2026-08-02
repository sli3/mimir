---
name: Mimir Dashboard
description: >-
  Cyberpunk operator-console design system for Mimir, a passive RF
  spectrum scanner: dark CRT terminal surfaces, neon accent colours,
  and an all-monospace type system across three routes.
colors:
  bg-root: "#080F14"
  bg-panel: "#0A1520"
  bg-header: "#050C11"
  bg-deep: "#030810"
  border: "#1A3040"
  border-active: "#00FFFF"
  border-alert: "#FF4444"
  neon-cyan: "#00FFFF"
  neon-green: "#00FF88"
  neon-amber: "#FFCC00"
  neon-magenta: "#FF66FF"
  neon-red: "#FF4444"
  text-primary: "#C8D8E0"
  text-dim: "#4A7A90"
  text-bright: "#aaddff"
  wf-noise: "#030810"
  wf-weak: "#003050"
  wf-low: "#006080"
  wf-mid: "#00A0C0"
  wf-signal: "#00E0E0"
  wf-strong: "#FFCC00"
  wf-peak: "#FF4400"
  wf-hot: "#FFFFFF"
  neon-white: "#ffffff"
typography:
  mimir-logo:
    fontFamily: Press Start 2P
    fontSize: 14px
    fontWeight: 700
    letterSpacing: 3px
  page-h1:
    fontFamily: Share Tech Mono
    fontSize: 18px
    fontWeight: 400
    letterSpacing: 2px
  data-mono:
    fontFamily: Share Tech Mono
    fontSize: 14px
    fontWeight: 400
  details-value:
    fontFamily: Share Tech Mono
    fontSize: 13px
    fontWeight: 700
  section-header:
    fontFamily: Share Tech Mono
    fontSize: 11px
    fontWeight: 400
    letterSpacing: 2px
  label-caps:
    fontFamily: Share Tech Mono
    fontSize: 10px
    fontWeight: 400
    letterSpacing: 1px
  micro-label:
    fontFamily: Share Tech Mono
    fontSize: 9px
    fontWeight: 400
    letterSpacing: 1px
rounded:
  none: 0px
  sm: 2px
  full: 9999px
spacing:
  xs: 2px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  2xl: 20px
  3xl: 24px
  4xl: 32px
components:
  section-header:
    backgroundColor: "{colors.bg-header}"
    textColor: "{colors.neon-cyan}"
    typography: "{typography.section-header}"
    height: 28px
  status-badge:
    textColor: "{colors.neon-green}"
    typography: "{typography.label-caps}"
    padding: 2px 8px
  band-button:
    textColor: "{colors.text-dim}"
    typography: "{typography.data-mono}"
    padding: 2px 6px
  tune-button:
    textColor: "{colors.neon-cyan}"
    typography: "{typography.data-mono}"
    padding: 3px 8px
  input-field:
    backgroundColor: "{colors.bg-header}"
    textColor: "{colors.neon-cyan}"
    typography: "{typography.data-mono}"
    padding: 3px 8px
  stat-tile:
    textColor: "{colors.text-dim}"
    typography: "{typography.micro-label}"
    rounded: "{rounded.sm}"
    padding: 2px 6px
  op-badge:
    textColor: "{colors.neon-cyan}"
    typography: "{typography.micro-label}"
    size: 28px
  details-row:
    textColor: "{colors.text-primary}"
    typography: "{typography.details-value}"
---

## Overview

Mimir's dashboard is an operator console, not a web app. Every
surface is a dark instrument panel: near-black backgrounds layered
in three depths, hairline blue-grey borders, and neon accents that
read like phosphor on a CRT. A global scanline overlay sweeps the
main route, reinforcing the feeling of watching live hardware
telemetry rather than browsing a page. Nothing is decorative for
its own sake; colour is always load-bearing, encoding signal state,
device health, or legal status at a glance.

The mood is disciplined density. Monospace type everywhere, sharp
corners, tight 2px-8px gutters, and fixed-height chrome (28px
section headers, 36px top bar, 56px band nav) give the interface
the rhythm of a terminal. Motion is restrained to a single blink
keyframe reserved for states that genuinely demand attention, and
glow is confined to thin box-shadows on active borders.

## Colors

The palette lives entirely in `dashboard/frontend/src/theme/cyberpunk.css`
as CSS custom properties on `:root`, grouped into background layers,
borders, neon accents, text, and an eight-stop waterfall ramp.

Background layers:

- **bg-root (#080F14):** Page background, the deepest working surface.
- **bg-panel (#0A1520):** Right-column panel stack and message cards.
- **bg-header (#050C11):** Section headers, top bar, and band nav chrome.
- **bg-deep (#030810):** Deepest layer, shared with the waterfall noise floor.

Borders:

- **border (#1A3040):** Default hairline between panels and tiles.
- **border-active (#00FFFF):** Focused or active control outline.
- **border-alert (#FF4444):** Alert-state outline.

Neon accents:

- **neon-cyan (#00FFFF):** Primary accent: headings, tuned states, links, data values.
- **neon-green (#00FF88):** Healthy, confirmed, legal, or positive-margin states.
- **neon-amber (#FFCC00):** Caution and counters (scan count, backlog, power).
- **neon-magenta (#FF66FF):** AI subsystem markers (AI REASONING header, LLM stats, chroma distance).
- **neon-red (#FF4444):** Alerts, anomalies, errors, and NOT-legal states.

Text:

- **text-primary (#C8D8E0):** Default body and readout text.
- **text-dim (#4A7A90):** Labels, subtitles, idle states, and placeholders.
- **text-bright (#aaddff):** Emphasised text variant (legacy token).

Waterfall ramp (noise to peak):

- **wf-noise (#030810):** Noise floor.
- **wf-weak (#003050):** Weak energy.
- **wf-low (#006080):** Low energy.
- **wf-mid (#00A0C0):** Mid energy.
- **wf-signal (#00E0E0):** Signal present.
- **wf-strong (#FFCC00):** Strong signal.
- **wf-peak (#FF4400):** Peak energy.
- **wf-hot (#FFFFFF):** Maximum, white-hot.

Legacy aliases kept for backward compatibility: `panel`, `panel-header`,
and `bg` alias the background tokens, `text` aliases `text-primary`,
and **neon-white (#ffffff)** duplicates the waterfall hot stop.

## Typography

Two font families carry the whole interface, both monospace. Share
Tech Mono (with Courier New fallback) is the universal workhorse,
assigned to both the `--font-display` and `--font-data` custom
properties, so headings, labels, data readouts, and body text all
share one voice. The single exception is the MIMIR logo in the top
header, set in Press Start 2P at 14px, bold, with 3px letter-spacing:
a pixel-font brand mark that breaks the grid on purpose.

The scale is compact and terminal-like. Body text sits at 14px.
Section headers and subtitles run at 11px with 2px letter-spacing.
Dense labels drop to 10px (details rows, badges) and 9px (stat-tile
labels), always uppercase with 1px letter-spacing. Data values in
the SIGNAL DETAILS panel are 13px bold and colour-keyed by meaning.
Page-level H1s on /vectordb and /radar are 18px, regular weight,
2px letter-spacing, in neon-cyan. Line-height is only loosened where
prose appears: 1.4 in the operator tooltip, 1.5 in vector-page
messages.

## Layout

Every route is a fixed 100vw x 100vh shell with `overflow: hidden`;
nothing scrolls at the page level, only panel interiors. The main
route (`/`) is a vertical flex column: a 36px top header (brand,
subtitle, RADAR link, clock), then a content row split between a
flexible left stack and a fixed 380px right column. The left stack
holds a 42vh block containing the 56px band nav bar, the main
waterfall, and the spectrometer strip, followed by the AI REASONING
panel (min-height 220px) and a three-column decoded-signals row
(SIGNAL INTERCEPT, RAW DECODE, FRAME INSPECTOR) separated by 1px
borders. The right column stacks SIGNAL DETAILS, SYSTEM STATUS,
and SIGNAL HISTORY full-height.

The /vectordb and /radar routes use a simpler two-row grid: an
auto-height page header (12px 20px padding, bottom border) over a
1fr content area that hosts the 3D scatter or the PPI scope. Both
suppress the global scanline overlay while mounted. Section chrome
is consistent everywhere: 28px headers on bg-header with a bottom
border, 10px horizontal padding, and 2px-8px internal gutters.

## Shapes

The design is deliberately angular. The default corner radius is
zero everywhere: panels, buttons, inputs, badges, and message cards
are all sharp rectangles, reinforcing the instrument-panel
character. Only two exceptions exist in the entire codebase.

System stat tiles (SDR STATUS, ACTIVE FREQ, SCAN COUNT, and peers
in the SYSTEM STATUS grid) use a 2px border-radius, the smallest
possible softening. Vector legend swatches on /vectordb are full
circles via `border-radius: 50%`, a functional choice for a scatter
plot legend rather than a stylistic one. Nothing else rounds.

## Components

**Section header.** A 28px strip on bg-header with a 1px bottom
border and 10px horizontal padding. Its label is 11px Share Tech
Mono, letter-spacing 2px, colour-keyed by domain: neon-cyan for
system sections, neon-amber for decoders, neon-magenta for AI,
neon-green for history. Optional right-aligned dim metadata text
shares the strip.

**Status badge.** An inline-flex pill-less rectangle: 1px solid
border in the state colour, 2px 8px padding, 10px letter-spaced
text, and a leading diamond glyph. Active alert states add a tinted
background, a soft glow via box-shadow, and the 1.2s blink
animation; the TUNED variant is neon-green and static; IDLE is
dim and borderless-subtle.

**Band button.** The band nav unit: 12px monospace label over an
11px MHz sub-label, 2px 6px padding, 1px border. Active state is a
neon-cyan border and text over a faint cyan fill; unsupported bands
fall to dim text at 0.35 opacity with the default border. Buttons
within a group sit 4px apart; groups are separated by a 1px
vertical divider.

**Tune button and input field.** The custom-frequency pair in the
band nav. The input is bg-header with a translucent cyan border,
neon-cyan 12px monospace text, and 3px 8px padding. The TUNE button
is a neon-cyan outline on a faint cyan fill, same padding and type,
with a play-glyph suffix.

**Stat tile.** The SYSTEM STATUS unit: 1px border, faint cyan
background tint, 2px border-radius, 2px 6px padding. A 9px
uppercase dim label sits over an 11px colour-keyed value (green for
status, cyan for frequency, amber for counters, magenta for LLM
stats). Tiles are spaced 4px apart in their grid rows.

**OP badge.** A 28px square with a 1px border in the current
operator-state colour, centring a 9px "OP" label. It anchors the
operator status row in SIGNAL DETAILS and exposes a 320px tooltip
(bg-header, bordered, line-height 1.4) on hover or focus.

**Details row.** The SIGNAL DETAILS pattern: a baseline-aligned
flex row with a 10px uppercase dim label on the left and a 13px
bold colour-keyed value on the right, separated from the next row
by a 1px dark divider and 5px vertical padding. The CONFIDENCE row
appends a 3px progress bar under the text.

**Vector message.** The /vectordb overlay card: max-width 520px,
24px 32px padding, bg-panel with a 1px border and a 3px neon-cyan
left accent, 16px text at line-height 1.5. The error variant swaps
the accent and text to neon-red; a blink variant animates at 1.5s.

**Legend panel and tooltip.** Floating /vectordb chrome: translucent
bg-header fill with backdrop blur, 1px border, and a 2px neon-cyan
left accent. The legend is 150px wide with 12px padding; the tooltip
is 220px wide with 10px 12px padding, 11px text, and a faint cyan
glow shadow.

## Do's and Don'ts

**Do** keep every text element in Share Tech Mono. The only
proportional-feeling exception in the codebase is the Press Start 2P
MIMIR logo, and it is deliberately confined to the header brand mark.

**Do** colour-key data values by meaning, not by preference. Green
means healthy or legal, amber means caution or counters, magenta
means AI subsystem, red means alert. The SIGNAL DETAILS panel and
SYSTEM STATUS tiles both follow this mapping.

**Don't** introduce border-radius above 2px. The design is
deliberately angular; the only rounded elements are the 2px stat
tiles and the circular legend swatches.

**Don't** add a third typeface or any proportional font. Both
`--font-display` and `--font-data` resolve to the same monospace
stack, and that uniformity is the voice of the interface.

**Don't** reach for drop shadows or elevation to separate layers.
Depth comes from the three background tones and hairline borders;
the only shadows in the codebase are small neon glows on active
states and tooltips.

**Don't** let the page scroll. All three routes are fixed 100vw x
100vh shells with overflow hidden; scrolling belongs inside panels,
never at the viewport.
