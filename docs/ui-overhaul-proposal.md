# UI overhaul: design review and proposal (rf#78)

Status: proposal for Prin to agree. No code has changed. Each card at the end
is a separate small build with its own browser check.

## How the review was done

- On 2026-11-28 pm looked at all four pages on the demo: `/` (dashboard),
  `/radar`, `/vectordb` and `/replay`. The routes are the ones in
  `dashboard/frontend/src/AppRouter.jsx`.
- Browser: Chrome at `localhost:5173`. The demo backend replayed
  `capture_1090000000hz_20260910_100910`, a 1090 MHz ADS-B capture recorded on
  the Pluto.
- No console errors on any page. Capture Now and Record were not clicked.
- Not seen: the FM, aviation, ACARS, AIS, APRS and ISM views. The demo replays
  only ADS-B, and the other band buttons are greyed out for the Pluto profile.
  Nothing below claims how those bands look.

## Findings

### Readability (all pages)

- Most labels use `--text-dim: #4A7A90` on `--bg-panel: #0A1520`
  (`dashboard/frontend/src/theme/cyberpunk.css`). By pm's calculation that is
  about 3.9:1 contrast. The common accessibility target for small text is
  4.5:1.
- Text is small throughout:
  - inline `fontSize` values in components and pages run from 9 to 13 px;
  - `font-size` in `RadarPage.css`, `ReplayPage.css` and
    `VectorSpacePage.css` runs from 9 to 18 px, with several 9 and 10 px rules.
  - Share Tech Mono is a thin face, so 9 to 11 px dim labels are hard to read.
- Observed:
  - the SIGNAL DETAILS labels (DEVICE, FREQUENCY, SNR ...);
  - the SYSTEM STATUS cell labels;
  - the radar table header;
  - the empty-state text ("No in-range contacts", "No aircraft selected");
  - the greyed-out band buttons, which are close to invisible.

### Navigation

- Only the dashboard has page links. `components/HeaderBar.jsx` shows RADAR,
  VECTOR SPACE and REPLAY as plain anchors, each with its own inline style.
- `/radar`, `/vectordb` and `/replay` each have their own header
  (`radar-header`, `vector-header`, `replay-header`) with no links. The only
  way back to the dashboard or across to another page is the browser's back
  button.

### Status colours that mislead

- AU LEGAL shows `legal_rx` in red. `components/SignalDetailsPanel.jsx` line
  121 colours the value green only when it `.includes('LEGAL')`, which is a
  case-sensitive check, and the value arrives in lower case. So a signal that
  is legal to receive is shown in the alarm colour.
- SDR STATUS shows DISCONNECTED in red in demo mode.
  `components/SystemStatusPanel.jsx` line 47 shows `DISCONNECTED` whenever
  `hackrf_status` is empty. In the demo, which opens no SDR on purpose, that
  reads like a fault.

### Empty states and panels that do not apply

- Dashboard:
  - There is a large empty band under the single waterfall strip, above the
    spectrometer.
  - The ADS-B panel listed aircraft 7C7BCC while `/radar` said "0 CONTACTS"
    and "No in-range contacts". The capture's aircraft sends velocity frames
    but no position, so it cannot be plotted. The radar does not say that
    aircraft are heard but have no position yet.
- Radar: "No aircraft selected" appears twice: in the detail panel, and in the
  prediction area below the scope. Both are small and dim, and the large
  areas around them are empty.
- Vector space:
  - The legend shows raw label keys (`fm_broadcast`, `ism_915`,
    `aviation_vhf`) rather than the band names used elsewhere (FM, ISM,
    AVIATION).
  - It lists bands that have no points in the store, with no counts.
- Replay:
  - The capture list has no column headings and no grouping by band or
    device, and the mode tag (`[record]` / `[oneshot]`) is dim at the far
    right.
  - There is no line explaining what selecting a capture does.

### What works and should stay

- The cyberpunk look: dark panels, neon accents, Share Tech Mono, and the
  Press Start 2P logo in the header only.
- The dashboard's band-aware decoded panels: only the ADS-B panels showed at
  1090 MHz.
- The vector space legend panel and header stats layout.

## Proposals

1. **One shared nav bar.**
   - A single nav component on all four pages: the MIMIR logo, the links
     DASHBOARD, RADAR, VECTOR SPACE and REPLAY, the current page highlighted,
     and the clock.
   - It replaces the dashboard's link block. Each page keeps its own title
     line below it.
   - The link style is defined once, not repeated inline.
2. **Readability tokens.**
   - Add font-size tokens to `cyberpunk.css` (for example label, body and
     title) with an 11 px floor for labels.
   - Lighten `--text-dim` until dim text on `--bg-panel` reaches at least
     4.5:1.
   - Raise greyed-out band buttons enough to read.
   - Keep the palette, the fonts and the neon accents.
3. **Honest status colours.** Fix the AU LEGAL check so `legal_rx` is green,
   and show DEMO rather than a red DISCONNECTED when the backend is in demo
   mode.
4. **Empty states that explain.**
   - Radar: say when aircraft are heard but have no position, with the count.
   - Show one "select an aircraft" prompt, not two.
5. **Pages that read at a glance.**
   - Replay: column headings, grouping by band, a one-line explanation.
   - Vector space: band names and per-band counts in the legend, hiding bands
     with no points.
   - Dashboard: close the empty band under the single waterfall strip.

## Build cards

All are frontend-only, so none trips the hardware gate unless noted. None
renames or merges a SocketIO event or field. Any card that touches the radar
rates must keep the naming trap in mind: `delta_r_deg_per_sec` is the bearing
rate in deg/s, and `deltaRNmPerSec` is the range rate in nm/s.

1. **Shared nav bar.**
   - Scope: a new nav component, used by `DashboardPage`, `RadarPage`,
     `VectorSpacePage` and `ReplayPage`; `HeaderBar.jsx` slimmed.
   - Browser check: each page shows the bar with its own link highlighted;
     every link opens the right page; the dashboard header still shows the
     logo and clock.
2. **AU LEGAL colour fix.**
   - Scope: `SignalDetailsPanel.jsx`, plus a Vitest case for a lower-case
     `legal_rx` value.
   - Browser check: on the demo, AU LEGAL `legal_rx` shows green.
3. **Readability tokens.**
   - Scope: `cyberpunk.css` tokens, then the smallest dim labels on the
     dashboard (signal details, system status, band buttons).
   - Browser check: before and after screenshots of the dashboard; no layout
     overflow at 1568 px wide.
4. **Readability on the other pages.**
   - Scope: `RadarPage.css`, `ReplayPage.css` and `VectorSpacePage.css`
     switched to the new tokens.
   - Browser check: before and after screenshots of each page.
5. **Demo SDR status.**
   - Scope: first find what the demo backend sends as `hackrf_status`. If the
     fix needs a backend change, the card is re-planned. If it needs
     `scan.py`, it is hardware-pending.
   - Browser check: the demo shows DEMO, not a red DISCONNECTED.
6. **Radar empty states.**
   - Scope: `RadarPage.jsx` and the radar panels: a "heard, no position yet"
     count, and one selection prompt.
   - Browser check: on the demo capture, the radar explains why it shows no
     contacts.
7. **Replay list.**
   - Scope: `ReplayPage.jsx` and its CSS: column headings, grouping by band,
     an explanation line.
   - Browser check: `/replay` lists the captures with headings and groups;
     opening a capture still works.
8. **Vector space legend.**
   - Scope: `VectorSpacePage.jsx` and `utils/vectorColours.js`: band names,
     per-band counts, hiding empty bands.
   - Browser check: the legend matches the points shown.
9. **Dashboard spacing.**
   - Scope: `WaterfallPanel.jsx` and `DashboardPage.jsx` layout only.
   - Browser check: no empty band under a single waterfall strip; the
     multi-band layout is unchanged.

Suggested order: 2 (a quick, clear bug), then 1, 3 and 4, then 6, 7 and 8,
with 5 and 9 last. Cards are created on the board only once Prin agrees.
