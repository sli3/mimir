---
name: generate-design
description: >-
  Generate new screens from text prompts or images, edit existing screens
  with prompts and design system tokens, and generate design variants using
  Stitch MCP. Includes prompt enhancement pipeline, design mappings, professional
  UI/UX terminology, design tokens and theme system capabilities.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Generate Design

Create new design screens from text descriptions, images, or mockups, edit
existing screens with prompts and design system tokens, and generate design
variants using Stitch MCP.

## Mimir dependency note — read before using

This skill's own rule is: **if a project-level design system exists, never
put colors/fonts/theme instructions in the generation prompt — the design
system applies them automatically.** For Mimir, that project-level design
system is only real once `.stitch/DESIGN.md` (produced by `extract-design-md`)
has actually been **applied** to a Stitch project via the `manage-design-system`
skill — which has not been ported to this project as of this writing. Until
that step exists and has been run:

- `stitch_list_design_systems` will return empty for the Mimir project
- Every `generate-design` call is working from Stitch's default aesthetic,
  not Mimir's extracted one
- This is the actual mechanism behind the "as similar as possible" goal from
  the integration plan — `extract-design-md` alone does not achieve it; the
  chain is extract → apply (`manage-design-system`) → generate

Confirm a design system exists (Step 2 of "Generate from Text Flow" below)
before assuming generated screens will match Mimir's real visual language.

## 🎨 Prompt Enhancement Pipeline

Before calling any Stitch generation or editing tool, you MUST enhance the
user's prompt.

### 1. Analyze Context

- **Project**: Use `stitch_list_projects` to find the correct `projectId`. If
  no suitable project exists, create one using `stitch_create_project`.
- **Design System**: Check if a design system exists for the project via
  `stitch_list_design_systems`. If one exists, design tokens (colors, fonts,
  roundness) are already applied at the project level — do NOT include any
  color, font, or theme instructions in the generation prompt. If none
  exists, delegate to the **manage-design-system** skill first before
  generating screens (not yet available on this project — see note above).

### 2. Refine UI/UX Terminology

> **Reference gap — flagged, not resolved:** the upstream skill points to
> `references/design-mappings.md` and `references/prompt-keywords.md` for
> vocabulary substitution and `examples/enhanced-prompt.md` for a worked
> example. None of these were included in what was ported here. This is
> optional polish, not core logic — the skill works without them, using the
> general enhancement guidance below, but prompts may be less refined than
> the original author intended until the real reference files are sourced.

Replace vague terms with specific, professional UI/UX terminology where you
can:

- Vague: "Make a nice header"
- Professional: "Sticky navigation bar with glassmorphism effect and centered
  logo"

### 3. Structure the Final Prompt

Format the enhanced prompt for Stitch. Focus exclusively on **layout, content,
and structure** — never include colors, fonts, or theme instructions (these are
handled by the manage-design-system skill at the project level, once that
chain is in place).

For **new screens**, use this template:

```markdown
[Overall purpose and user intent of the page]

**PLATFORM:** [Web/Mobile], [Desktop/Mobile]-first

**PAGE STRUCTURE:**
1. **Header:** [Description of navigation and branding]
2. **Hero Section:** [Headline, subtext, and primary CTA]
3. **Primary Content Area:** [Detailed component breakdown]
4. **Footer:** [Links and copyright information]
```

For a Mimir instrument panel (e.g. `/vectordb`, `/radar`), adapt the template
to the actual sections that page has — there is no "hero section" on a data
dashboard; describe the real panels instead (controls, live view, legend,
detail/inspector area).

For **edits**, be specific about what to change:

- **Location**: "Change the [primary button] in the [hero section]..."
- **Visuals**: "...to a darker blue (#004080) and add a subtle shadow."
- **Structure**: "Add a secondary button next to the primary one with the text
  'Learn More'."

> **Caution:** Do NOT include hex codes, font names, color palettes, roundness
> values, or any design system tokens in a **generation** prompt. These are
> applied at the project level by the manage-design-system skill and will
> conflict if duplicated. (For **edit** prompts, hex codes are acceptable for
> precise color adjustments.)

### 4. Present AI Insights

After any tool call, always surface the `outputComponents` (Text Description
and Suggestions) to the user.

---

## Steps

### Determine the Mode

Decide which flow to use based on the user's request:

- User wants to create from a text description → **Generate from Text** flow
- User provides an image, screenshot, or mockup → **Generate from Image** flow
- User wants to modify an existing screen → **Edit** flow
- User wants layout/color/content variations → **Generate Variants** flow

---

### Generate from Text Flow (New Screen)

#### 1. Enhance the User Prompt

Apply the Prompt Enhancement Pipeline above.

#### 2. Identify the Project

Use `stitch_list_projects` to find the correct `projectId` if it is not
already known.

#### 3. Generate the Screen

Call the `stitch_generate_screen_from_text` tool with the enhanced prompt and
the `designSystem` ID (if found in Step 1).

```json
{
  "projectId": "...",
  "prompt": "[Your Enhanced Prompt]",
  "designSystem": "assets/...", // Optional: Pass if found in Step 1
  "deviceType": "DESKTOP"  // Options: MOBILE, DESKTOP, TABLET
}
```

#### 4. Present AI Feedback

Always show the text description and suggestions from `outputComponents` to the
user.

#### 5. Download Design Assets

After generation, download the HTML and screenshot urls from `outputComponents`
to the `.stitch/designs` directory.

- **Naming**: Use the screen ID or a descriptive slug for the filename.
- **Tools**: Use `curl -o` via `bash`.
- **Directory**: Ensure `.stitch/designs` exists.

#### 6. Review and Refine

- If the result is not exactly as expected, continue with the **Edit** flow
  to make targeted adjustments.
- Do NOT re-generate from scratch unless the fundamental layout is wrong.

---

### Generate from Image Flow (Image/Mockup → Design)

Use this flow when the user provides an image, screenshot, or design mockup to
recreate in Stitch.

#### 1. Identify the Project

Use `stitch_list_projects` to find the correct `projectId`. If no suitable
project exists, create one using `stitch_create_project`.

#### 2. Upload the Image

Delegate to the **upload-to-stitch** skill to upload the image to the project
(not yet ported to this project). This creates a new screen with the image as
its content.

#### 3. Refine with Edit

Once uploaded, use `stitch_list_screens` to find the newly created `screenId`,
then call `stitch_edit_screens` with a descriptive prompt to refine the
design:

```json
{
  "projectId": "...",
  "selectedScreenIds": ["<uploaded-screen-id>"],
  "prompt": "[Describe what to adjust, enhance, or recreate from this mockup]"
}
```

> **Tip:** For best results, describe the intent behind the image rather than
> just saying "make it look like this". For example: "This is a dashboard
> mockup — recreate it with a proper data table, sidebar navigation, and
> chart widgets."

#### 4. Present AI Feedback

Always show the text description and suggestions from `outputComponents` to the
user.

#### 5. Download Design Assets

Download the HTML and screenshot urls from `outputComponents` to the
`.stitch/designs` directory.

- **Naming**: Use the screen ID or a descriptive slug for the filename.
- **Tools**: Use `curl -o` via `bash`.
- **Directory**: Ensure `.stitch/designs` exists.

---

### Edit Flow (Modify Existing Screen)

#### 1. Identify the Screen

Use `stitch_list_screens` or `stitch_get_screen` to find the correct
`projectId` and `screenId`.

#### 2. Formulate the Edit Prompt

Apply the Prompt Enhancement Pipeline, focusing on specificity:

- **Location**: "Change the color of the [primary button] in the [hero
  section]..."
- **Visuals**: "...to a darker blue (#004080) and add a subtle shadow."
- **Structure**: "Add a secondary button next to the primary one with the text
  'Learn More'."

#### 3. Apply the Edit

Call the `stitch_edit_screens` tool.

```json
{
  "projectId": "...",
  "selectedScreenIds": ["..."],
  "prompt": "[Your targeted edit prompt]"
}
```

#### 4. Present AI Feedback

Always show the text description and suggestions from `outputComponents` to the
user.

#### 5. Download Design Assets

After editing, download the updated HTML and screenshot urls from
`outputComponents` to the `.stitch/designs` directory, overwriting previous
versions to ensure the local files reflect the latest edits.

- **Naming**: Use the screen ID or a descriptive slug for the filename.
- **Tools**: Use `curl -o` via `bash`.
- **Directory**: Ensure `.stitch/designs` exists.

#### 6. Update Project Metadata

After downloading assets, update `.stitch/metadata.json` to reflect any changes
(e.g., updated screen titles or new screen IDs from the edit). The metadata
file tracks all screens, their device types, and design system info (format
depends on the **manage-design-system** skill, not yet ported).

#### 7. Verify and Repeat

- Check the output screen to see if the changes were applied correctly.
- If more polish is needed, repeat the edit flow with a new specific prompt.

---

### Generate Variants Flow (Explore Variations)

Use this flow when the user wants to explore alternative layouts, color schemes,
or content variations of an existing screen.

#### 1. Identify the Screen

Use `stitch_list_screens` or `stitch_get_screen` to find the correct
`projectId` and `screenId`.

#### 2. Configure Variant Options

Call the `stitch_generate_variants` tool with the appropriate options:

```json
{
  "projectId": "...",
  "selectedScreenIds": ["..."],
  "prompt": "[Describe the direction for variants]",
  "variantOptions": {
    "variantCount": 3,
    "creativeRange": "EXPLORE",
    "aspects": ["LAYOUT", "COLOR_SCHEME"]
  }
}
```

**Variant Options:**
- **`variantCount`**: 1–5 variants (default: 3)
- **`creativeRange`**: `REFINE` (subtle), `EXPLORE` (balanced), or `REIMAGINE`
  (radical)
- **`aspects`**: Focus on specific dimensions — `LAYOUT`, `COLOR_SCHEME`,
  `IMAGES`, `TEXT_FONT`, `TEXT_CONTENT`, or leave empty for all

#### 3. Present AI Feedback

Always show the text description and suggestions from `outputComponents` to the
user.

#### 4. Download Design Assets

Download the variant HTML and screenshot urls from `outputComponents` to the
`.stitch/designs` directory.

- **Naming**: Use the screen ID or a descriptive slug for the filename.
- **Tools**: Use `curl -o` via `bash`.
- **Directory**: Ensure `.stitch/designs` exists.

---

## 💡 Tips

- **Be structural**: Break the page down into its real sections (for Mimir:
  controls, live view, legend/detail panel — not generic marketing-site
  sections) in your prompt.
- **Content first**: Describe what each section contains (text, images,
  data panels) rather than how it looks.
- **Iterative Polish**: Prefer editing for targeted adjustments over full
  re-generation.
- **No theme leakage**: Never put hex codes, font names, or color roles in a
  generation prompt — the design system handles all visual styling, once
  `manage-design-system` has actually applied one (see dependency note above).
- **Specify interactions**: Mention hover states, animations, and click behavior
  rather than visual styling.
- **Keep edits focused**: One edit at a time is often better than a long list of
  changes.
- **Reference components**: Use professional terms like "navigation bar", "hero
  section", "footer", "card grid" — or the real Mimir equivalents.
- **Precise colors in edits**: Use hex codes for exact color matching when
  editing existing screens.
- **Remember the A/B routing rule** (per the integration plan): output from
  this skill is always a visual/HTML reference. Whether it becomes hand-written
  React (senior-dev, Option A) or auto-converted via `react-components`
  (Option B) depends on whether the target component reads live
  scanner/ChromaDB/BAND_PROFILES data — that decision is not made by this
  skill.

## Compatibility notes (OpenCode / Mimir)

- All bare tool names (`list_projects`, `generate_screen_from_text`,
  `edit_screens`, `create_project`, `list_design_systems`,
  `generate_variants`, `list_screens`, `get_screen`) replaced with confirmed
  real names using the `stitch_` prefix (underscore, no colon) — the upstream
  file deferred to "your system prompt" for prefix handling, which does not
  apply in this project's setup; the real names are used directly instead.
- `run_command`/`curl -o via run_command` → `bash`.
- Three optional reference/example files were not available to port
  (`references/design-mappings.md`, `references/prompt-keywords.md`,
  `examples/enhanced-prompt.md`) — flagged inline, not blocking.
- Added the explicit dependency-chain note at the top: this skill's
  "no theme leakage" behavior only produces Mimir-consistent results once
  `manage-design-system` (not yet ported) has applied the extracted design
  system to the Stitch project.
