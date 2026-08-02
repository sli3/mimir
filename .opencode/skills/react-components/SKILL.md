---
name: react-components
description: >-
  Converts Stitch designs into modular Vite and React components, or syncs/updates
  existing React components to align with the latest Stitch designs, using system-level
  networking and AST-based validation.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Stitch to React Components

You are a frontend engineer focused on transforming designs into clean React code or syncing/updating existing React components to align with the latest Stitch designs. You follow a modular approach and use automated tools to ensure code quality.

> **CRITICAL: Every step in this skill is MANDATORY. Do NOT skip any step or take shortcuts. Each section contains a GATE that must be satisfied before proceeding.**

## What this validator does — and does not — check (Mimir note)

Read this before treating a `npm run validate` pass as a full correctness
signal. The included `validate.js` mechanically checks exactly two things:

1. Does a `[ComponentName]Props` TypeScript interface exist
2. Are there hardcoded hex colors in `className` attributes

It does **not** check hook isolation, `href="#"` → `<Link>` conversion, dark
mode variants, or — critically for Mimir — **whether the component's data
bindings match a real backend contract**. A component can pass this
validator cleanly while reading `data.value` instead of the real
`meta.get("center_freq_hz", meta.get("freq_hz"))` fallback your
`dashboard/server.py` actually needs, or while having no handling at all for
the `status: "empty"` state `/api/vectorstore/points` returns before
ChromaDB is seeded. This validator is a real, useful mechanical check — but
it is not a substitute for `senior-dev` verifying data-binding correctness
against the actual endpoint contract. Per the project's integration plan,
any component reading live scanner/ChromaDB/BAND_PROFILES data should not
rely on this validator alone as its safety net.

## Phase 1: Retrieval and networking

> **GATE: Phase 1 is complete ONLY when all screens have been downloaded via `scripts/fetch-stitch.sh` AND visually audited. Reading local files directly without going through this phase is PROHIBITED.**

1. **Metadata fetch**: Call `stitch_get_screen` for **EVERY screen** in the project to retrieve the design JSON with download URLs. Do NOT skip any screen.
2. **Check for existing designs**: Before downloading, check if `.stitch/designs/{page}.html` and `.stitch/designs/{page}.png` already exist:
   - **If files exist**: Ask the user whether to refresh the designs from the Stitch project using the MCP, or reuse the existing local files. **You MUST ask — do not assume.** Only re-download if the user confirms.
   - **If files do not exist**: Proceed to step 3.
3. **High-reliability download**: Internal AI fetch tools can fail on Google Cloud Storage domains. You MUST use the provided script.
   - **HTML**: `bash .opencode/skills/react-components/scripts/fetch-stitch.sh "[htmlCode.downloadUrl]" ".stitch/designs/{page}.html"`
   - **Screenshot**: Append `=w{width}` to the screenshot URL first, where `{width}` is the `width` value from the screen metadata (Google CDN serves low-res thumbnails by default). Then run: `bash .opencode/skills/react-components/scripts/fetch-stitch.sh "[screenshot.downloadUrl]=w{width}" ".stitch/designs/{page}.png"`
   - This script handles the necessary redirects and security handshakes.
4. **Visual audit**: Review the downloaded screenshot (`.stitch/designs/{page}.png`) to confirm design intent and layout details. **You MUST view each screenshot** — do not proceed based on assumptions about the design.
5. **Project metadata tracking**: Retrieve project configuration using `stitch_get_project` and save it to `.stitch/metadata.json`. Ensure it has:
   - `projectId`, `title`, `deviceType`
   - A `Last Sync Time` field matching the current sync ISO execution time
   - A `screens` map detailing each screen's ID, label, sourceScreen reference, dimensions, and canvasPosition.

### Anti-patterns for Phase 1
- ❌ Reading `.stitch/designs/*.html` directly without calling MCP `stitch_get_screen` first.
- ❌ Skipping the `fetch-stitch.sh` download script.
- ❌ Not asking the user when existing files are found.
- ❌ Skipping the visual audit of `.png` screenshots.
- ❌ Failing to generate or update `.stitch/metadata.json` and its `Last Sync Time` field upon syncing.

## Phase 2: Style extraction

> **GATE: Phase 2 is complete ONLY when `resources/style-guide.json` has been updated with tokens extracted from the current project's HTML `<head>`. Tokens from a previous project are NOT acceptable.**

1. **Extract `tailwind.config`**: Open each downloaded HTML file and locate the `tailwind.config` object in the `<head>` `<script>` block. Extract:
   - All color tokens
   - Font families
   - Spacing values
   - Border radius values
   - Font size/typography tokens
2. **Sync `resources/style-guide.json`**: Overwrite the file with the extracted tokens from THIS project. The style guide MUST match the Stitch project being converted. (No `resources/style-guide.json` template was available to port — create this file fresh, following the token categories above, rather than assuming a prior structure.)
3. **Verify sync**: Confirm the primary color, font families, and spacing in the updated `style-guide.json` match what you extracted.

### Anti-patterns for Phase 2
- ❌ Using `style-guide.json` as-is without verifying it matches the current project.
- ❌ Using hardcoded hex values in components instead of theme-mapped classes.

## Phase 3: Architectural rules

> **GATE: Every component MUST satisfy ALL of the following rules. Only the Props-interface and hardcoded-hex rules are mechanically enforced by `npm run validate` — see the note at the top of this file.**

* **Modular components**: Break the design into independent files. **Each reusable UI pattern** (cards, badges, pagination, search bars) MUST be extracted into its own component in `src/components/`. Monolithic page files that contain everything are PROHIBITED.
* **Logic isolation**: Move event handlers and business logic into custom hooks in `src/hooks/`. Examples: pagination logic → `usePagination`, filtering → `useFilter`.
* **Data decoupling**: Move ALL static text, image URLs, and lists into `src/data/mockData.ts`. No hardcoded content in components. **For Mimir: this mock data is a placeholder, not a spec.** The real data-fetching logic connecting a component to `dashboard/server.py`'s actual endpoints must be added by `senior-dev` — see the note at the top of this file.
* **Type safety**: EVERY component file (including pages) MUST include a `Readonly` TypeScript interface named `[ComponentName]Props`. The validator checks for this — files without a Props interface will FAIL validation.
* **Project specific**: Focus on the target project's needs and constraints. Leave Google license headers out of the generated React components.
* **Navigation wiring**: Stitch screens are standalone pages with `href="#"` placeholder links. When building a multi-page React app:
    * Replace ALL `href="#"` anchors with React Router `<Link>` components pointing to the correct routes.
    * **Always make the app logo/title in the TopAppBar a `<Link to="/">`** so users can navigate home from any page. This is critical because Stitch bottom nav bars use `md:hidden` and are invisible on desktop — without a clickable logo, desktop users have no way to return to the home page.
    * Wire the bottom nav items and sidebar nav items to their corresponding routes using `<Link>` with active-state highlighting based on `useLocation()`.
* **Style mapping**: Use theme-mapped Tailwind classes from the synced `style-guide.json`. No arbitrary hex codes.
* **Dark mode**: Apply `dark:` variants to ALL color classes throughout every component.

### Anti-patterns for Phase 3
- ❌ Putting all UI in a single monolithic page file.
- ❌ Inline event handlers or business logic without hooks.
- ❌ Hardcoding text, URLs, or data in component files.
- ❌ Components without a `[Name]Props` interface.
- ❌ Using hex color values instead of theme tokens.
- ❌ Leaving `href="#"` links unconverted.
- ❌ Treating a `validate.js` pass as confirmation the component's real data
  bindings are correct — it does not check this (see top-of-file note).

## Phase 4: Execution steps

> **GATE: Phase 4 verification, audits, and validation checks are optional. You MUST ask the user's permission to proceed with validation scripts, running local dev servers, or automated browser testing.**

1. **Environment setup**: If `node_modules` is missing, run `npm install` to enable the validation tools. This skill's validator requires `@swc/core` — install with `npm install --save-dev @swc/core` in `dashboard/frontend/` if not already present (it is not part of the existing Mimir frontend dependencies as of this port).
2. **Data layer**: Create `src/data/mockData.ts` based on the design content — placeholder only, per the note above.
3. **Component drafting**: Use a component template as a base (no `resources/component-template.tsx` was available to port — construct components following the architectural rules in Phase 3 directly).
4. **Application wiring**: Update the project entry point to render the new components.
5. **Quality check (Optional - Ask User first)**:
    * Run `node .opencode/skills/react-components/scripts/validate.js <file_path>` for **EVERY** `.tsx` file in `src/components/` and `src/pages/` to report component validity (Props interface + hardcoded hex checks only).
    * Run `tsc --noEmit` to verify TypeScript compile status.
    * Obtain permission before starting the dev server with `npm run dev` or initiating visual browser audits to verify the live result.
    * **For Mimir specifically:** after mechanical validation passes, `senior-dev` must separately review the component's data-fetching logic against the real endpoint it targets — this is a required step, not optional polish, for any component reading live scanner/ChromaDB/BAND_PROFILES data (per the project's A/B routing rule).

### Anti-patterns for Phase 4
- ❌ Commencing dev server start or browser audits without user consent.
- ❌ Declaring task "done" without verifying code compiles.
- ❌ Declaring task "done" on validator pass alone for a data-connected component without the separate senior-dev data-binding review.

## Troubleshooting
* **Fetch errors**: Ensure the URL is quoted in the bash command to prevent shell errors.
* **Validation errors**: Review the AST report and fix any missing interfaces or hardcoded styles. The most common failure is a missing `Props` interface — every component (including pages) needs one.
* **Dead navigation links**: Stitch HTML uses `href="#"` placeholders everywhere. Every `<a href="#">` must be converted to a `<Link to="/route">` with a real route. Verify all nav items are clickable and lead to the correct page.
* **Stale style-guide.json**: If colors or fonts look wrong, the `style-guide.json` likely has tokens from a different project. Re-extract from the current HTML `<head>`.
* **`Cannot find module '@swc/core'`**: `npm install --save-dev @swc/core` in `dashboard/frontend/`.

## Compatibility notes (OpenCode / Mimir)

- Both scripts (`fetch-stitch.sh`, `validate.js`) ported **verbatim** —
  neither required code changes. `fetch-stitch.sh` is a simple `curl`
  wrapper; `validate.js` needs `@swc/core`, flagged above as a new dev
  dependency for `dashboard/frontend/`.
- All `[prefix]:tool_name`/`list_tools` discovery replaced with confirmed
  real tool names (`stitch_get_screen`, `stitch_get_project`).
- `resources/style-guide.json` template, `resources/component-template.tsx`,
  and `resources/architecture-checklist.md` were not available to port —
  flagged inline at each point they're referenced, with a fallback
  instruction rather than fabricated content.
- Added the top-of-file note and inline flags throughout Phases 3–4 on
  exactly what `validate.js` does and does not check — this is the most
  important addition for this project, since the validator's real scope is
  narrower than the SKILL.md's list of architectural rules might suggest,
  and Mimir's own risk profile (live hardware/data-connected components)
  depends on that distinction being understood, not assumed away.
