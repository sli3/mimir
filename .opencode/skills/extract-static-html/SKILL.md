---
name: extract-static-html
description: >-
  Extract self-contained static HTML from a built web application or React components by inlining CSS and images. Use this skill whenever you need to capture a specific UI state, share a static version of a page, or prepare assets for Stitch upload, even if the user just asks to 'save the HTML' or 'mock the view'.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Extract Static HTML

Extract a self-contained static HTML file from any web application.

## Mimir scope note — read before using

This skill's Strategy A (Puppeteer) is the documented default for this
project. Mimir's dashboard runs locally with no auth wall
(`dashboard/frontend/`, Vite dev server), which is exactly the case Strategy
A is built for. **The `--auth-script` flag exists in `snapshot.ts` but is
deliberately not documented in the usage examples below** — Mimir has no
known login gate, so there's no reason to reach for it, and it's a
code-execution hook (dynamically imports and runs a local script against the
live page) that's better left unused unless a genuine need arises. If a
future auth wall is added to the dashboard, revisit this decision explicitly
rather than reaching for `--auth-script` by habit.

This skill requires `puppeteer` installed — a real, sizeable new dependency,
separate from `@swc/core` (needed by the `react-components` skill). Not
currently part of `dashboard/frontend/`'s dependencies as of this port.

## Which Strategy to Use

You MUST ask the user to choose which strategy to use before proceeding. Present the options clearly, **recommend Strategy A** as the preferred default, and **provide a brief pros/cons summary** for each option to help them make an informed decision.

| | Strategy A (Puppeteer) | Strategy B (Browser Subagent) |
| :--- | :--- | :--- |
| **When** | App runs locally, no auth wall | Need to interact with page first (click, fill forms) |
| **Fidelity** | **Highest — computed styles resolved** | High — rendered DOM |
| **Setup** | **Zero — no mock needed** | Zero — no mock needed |
| **Framework** | **Any** | Any |
| **Output** | **Writes to file — no size limit** | May truncate in agent context |

> **Checkpoint — User Confirmation Required.**
> You **MUST** ask the user which strategy they prefer before proceeding.
> Present the comparison table above, recommend Strategy A as the default, and
> wait for explicit approval. Do **NOT** make the decision yourself or proceed
> until the user confirms.

For Mimir specifically, Strategy A is very likely the right default given the
dashboard runs locally with no auth wall — but the confirmation checkpoint
above still applies and should not be skipped just because this note
suggests an answer.

***

## Strategy A: Puppeteer Snapshot (Recommended)

Launches headless Chrome, captures the fully rendered DOM, and produces a self-contained HTML file with all CSS inlined and images as base64. Works with **any framework** — no MockPage.jsx needed.

### Prerequisites

- App running locally (`dashboard/frontend/`: `npm run dev`, default Vite
  port; confirm the actual port before running, don't assume 5173 without
  checking)
- Node.js with `puppeteer` available (check: `node -e "require('puppeteer')"`
  — install with `npm install puppeteer` in `dashboard/frontend/` if missing)

### Workflow

1.  **Start the App** and note the port.

    > **Checkpoint — User Confirmation Required.**
    > After starting the local server, you **MUST** pause and ask the user for
    > confirmation before running the snapshot script or launching a browser
    > subagent. Report the URL and port to the user so they can verify the app
    > is running and rendering correctly. Do **NOT** proceed to the snapshot
    > step until the user confirms.

2.  **Run the Snapshot Script**:
    ```bash
    npx tsx .opencode/skills/extract-static-html/scripts/snapshot.ts \
      --url http://localhost:5173 \
      --output .stitch/home.html \
      --wait 2000
    ```

3.  **Multiple pages** — run once per route (adjust for Mimir's actual
    routes, e.g. `/vectordb`, `/radar`):
    ```bash
    npx tsx .opencode/skills/extract-static-html/scripts/snapshot.ts \
      --url http://localhost:5173 --output .stitch/home.html --wait 2000
    npx tsx .opencode/skills/extract-static-html/scripts/snapshot.ts \
      --url http://localhost:5173/vectordb --output .stitch/vectordb.html --wait 2000
    npx tsx .opencode/skills/extract-static-html/scripts/snapshot.ts \
      --url http://localhost:5173/radar --output .stitch/radar.html --wait 2000 --html-class dark
    ```

4.  **Clean Up Dev Server**:
    If a local dev server was started specifically for snapshot extraction, make sure to stop the server process or terminate the background task once extraction is completed.


### Script Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--url` | *(required)* | URL to capture |
| `--output` | *(required)* | Output file path |
| `--wait` | `1000` | Extra wait (ms) after network idle. Increase for lazy-loading apps — consider a higher value for pages with live data (waterfall, ADS-B feed) that may take a moment to populate. |
| `--viewport` | `1280x800` | Viewport size as `WIDTHxHEIGHT` |
| `--html-class` | — | Class(es) for `<html>` element (e.g., `dark`) |
| `--remove-fixed` | `false` | Remove fixed/sticky elements (cookie banners, chat widgets) |
| `--full-height` | `false` | Resize viewport to full scroll height |
| `--title` | — | Override page title (set to the route path, e.g. `/vectordb`, `/radar`) |
| `--inline-canvas` | `false` | Convert `<canvas>` elements (ECharts, Chart.js, D3, Three.js render targets) to base64 `<img>` tags — relevant for Mimir's 3D vector space visualization |

`--auth-script` exists in the underlying script but is intentionally not
listed here — see the Mimir scope note at the top of this file.

### What It Does Automatically

- Captures all CSSOM rules from `document.styleSheets` (preserves dynamic Vite/Tailwind dev styles and CSS-in-JS)
- Inlines all `<link rel="stylesheet">` → `<style>` blocks
- Converts `<img>` `src` **and `srcset`** → base64 data URIs (skips external fonts)
- Inlines same-origin and relative icon font files (`@font-face`) as base64 data URIs so ligatures never render as ASCII text
- Inlines `<source srcset>` URLs as base64
- Removes failed/dead `srcset` entries so the browser falls back to the inlined `src`
- Removes `<script>` tags, Vite HMR dev style blocks (`createHotContext`, `import.meta.hot`), and dev overlays
- Resolves relative CSS `url()` paths before inlining

### Framework Notes

For Mimir (React + Vite): works out of the box, `--wait 1000` as a starting
point — increase if live-data panels need more time to populate before
capture.

### Troubleshooting

| Issue | Solution |
| :--- | :--- |
| Images missing | Increase `--wait` |
| Images show as broken after server stops | Verify `srcset` was inlined — check log for "Inlined N images". If `srcset` URLs failed, they are auto-removed so `src` (inlined) is used. |
| Icons display as text / Serif unstyled font | Ensure `snapshot.ts` captures CSSOM from `document.styleSheets` (step 0) and same-origin icon fonts (`@font-face`) are inlined as base64 data URIs. |
| Dark mode not applied | `--html-class dark` |
| Cookie banner in output | `--remove-fixed` (not expected to be relevant for Mimir, no known cookie banner) |
| Charts/graphs show as blank boxes | Use `--inline-canvas` to serialize `<canvas>` to base64 `<img>` — relevant for the vector-space 3D view if it renders via canvas |
| `Cannot find module 'puppeteer'` | `npm install puppeteer` in `dashboard/frontend/` |

***

## Strategy B: Browser Subagent Capture

Use when you need to **interact with the page** (click buttons, fill forms, navigate tabs) before capturing. The browser subagent gives you full control but output may truncate for large pages.

### Workflow

1.  **Start the App** locally.
2.  **Navigate** using a browser subagent — for this project, the existing
    Playwright MCP connection (already scoped to `frontend-reviewer`) may be
    the right tool for the navigation/interaction step rather than a
    separate browser subagent, if one is available in context.
3.  **Interact** as needed (click, scroll, fill forms).
4.  **Extract DOM**: `document.documentElement.outerHTML`

    > **Warning:** Large pages may truncate. To handle this:
    > - Remove `<style>` tags before extraction: `document.querySelectorAll('style').forEach(el => el.remove())`
    > - Re-add styles statically (Tailwind CDN link, source CSS)
5.  **Save** to file.

***

## Appendix: Static Fallback (MockPage.jsx)

> **Last resort** for when the app cannot run locally (broken deps, missing backend, auth walls with no bypass). It requires manually flattening React components into a single JSX file. **Prefer Strategy A whenever possible.** Not expected to be needed for Mimir under normal circumstances, since the dashboard runs locally without an auth wall — documented here for completeness in case it's ever needed.

### When to Use

- App can't run locally at all
- Page requires auth with no mock/bypass
- You need a specific UI state that's impossible to reach by navigation (error screens, empty states — e.g. `/vectordb`'s pre-seed `status: "empty"` state, if it can't be reached by simply visiting the page before ChromaDB is seeded)

### Quick Reference

```bash
npx tsx .opencode/skills/extract-static-html/scripts/extract_inline_html.ts \
  --index-css src/css/App.css \
  --extra-css index.html \
  --outdir .stitch \
  --page src/MockPage.jsx:Page.html:"Page Title"
```

**Key flags**: `--no-tailwind` (non-Tailwind apps), `--html-class dark` (dark mode), `--css-files` (extra CSS files).

**Auto-detection**: Tailwind config is auto-detected. `@apply` directives automatically use `<style type="text/tailwindcss">`.

### MockPage.jsx Rules

1. **Include the full layout** — header, sidebar, footer (read the app's root component first)
2. **Flatten all conditionals** — pick one state, remove all ternaries and `&&` guards
3. **Hardcode all data** — replace `{variable}` with concrete values, unroll `.map()` loops. **For Mimir: use plausible-looking but clearly-fake placeholder values for anything resembling real signal data (SNR, frequency, confidence) — do not fabricate numbers that could be mistaken for real calibration results**, consistent with the `taste-design` skill's ban on invented metrics.
4. **Preserve logos** — use `<img>` with local paths (post-process will inline them)
5. **Remove floating elements** — cookie banners, chat widgets, feedback buttons (not expected to be relevant for Mimir)

### Post-Processing

Inline local images:
```bash
npx tsx .opencode/skills/extract-static-html/scripts/post_process.ts \
  .stitch/Page.html --base-dir <app-directory>
```

## Compatibility notes (OpenCode / Mimir)

- All three scripts (`snapshot.ts`, `extract_inline_html.ts`,
  `post_process.ts`) ported **verbatim** — none required code changes. All
  script invocation paths updated to
  `.opencode/skills/extract-static-html/scripts/`.
- `snapshot.ts` requires `puppeteer`; `extract_inline_html.ts` requires
  `@babel/parser`, `@babel/traverse`, `@babel/generator` — new dependencies
  for `dashboard/frontend/`, not currently present as of this port.
- `--auth-script` deliberately not surfaced in documented usage (see Mimir
  scope note at top of file) — Mimir has no known auth wall, and this is a
  code-execution hook better left unused without a specific need.
- Both `extract_inline_html.ts` and its outbound-fetch logic include real
  SSRF protection (`isSafeUrl`), blocking requests to localhost and private
  IP ranges — relevant since these scripts parse and fetch URLs found in
  HTML/JSX source, which could in principle point anywhere.
- Framework Notes table trimmed to React + Vite only (Mimir's actual stack)
  — the upstream table covering Next.js, Angular, Vue, Svelte, Storybook was
  dropped as not applicable, rather than carried forward as noise.
