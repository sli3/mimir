---
name: manage-design-system
description: >-
  Manage design systems in Stitch using MCP tools. Includes retrieval of assets,
  creating/updating design systems in Stitch, and applying them to screens.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Design-System

Create a "source of truth" for your project's design language to ensure
consistency across all future screens.

## Mimir chain note — why this skill matters

This is the piece that makes `extract-design-md`'s output actually count for
anything. Without this skill actually running, `.stitch/DESIGN.md` is just a
file on disk — `generate-design` has no way to know it exists, and every
generated screen uses Stitch's default aesthetic rather than Mimir's real
one. This skill is what turns the extracted document into a project-level
Stitch design system that `generate-design` automatically applies.

## 📥 Retrieval

To analyze a Stitch project, you must retrieve metadata and assets using the
Stitch MCP tools:

1. **Project lookup**: Use `stitch_list_projects` to find the target
   `projectId`.
2. **Screen lookup**: Use `stitch_list_screens` for that `projectId` to find
   representative screens (e.g., "Home", "Vector Space", "Radar").
3. **Metadata fetch**: Call `stitch_get_screen` for the target screen to get
   `screenshot.downloadUrl` and `htmlCode.downloadUrl`.
4. **Asset download**: Use `webfetch` to fetch the HTML code.

## 🧠 Synthesis from Description

If you need to extract a design system from existing screens, use the
`design-md` skill (already ported to this project).

To bootstrap from Mimir's **existing source code** rather than a rendered
Stitch screen, use the `extract-design-md` skill instead (also ported) — this
is the primary path for this project, since Mimir already has a real,
established frontend.

If there are no existing screens (new project), or a direct description is
given (e.g., "dark theme, blue and purple, rounded, Inter font"):

1. Map vague terms to precise values using the guidance in the `design-md`
   or `generate-design` skills.
2. Select concrete hex codes, font families, and roundness values.
3. Generate the `DESIGN.md` file (structure defined in the `design-md`
   skill).
4. Proceed to "Create or Update Design System in Stitch" below.

## 📝 Output Structure

The `DESIGN.md` file should follow the structure defined in the `design-md`
skill (already ported to this project — see
`.opencode/skills/design-md/SKILL.md`).

## 🚀 Create or Update Design System in Stitch

After generating `.stitch/DESIGN.md`, create or update the design system in
Stitch.

> **Checkpoint — User Confirmation Required.**
> Before uploading, you **MUST** pause and ask the user for confirmation.
> Present a summary of the design system you are about to create (display
> name, key colors, fonts, and roundness) and wait for explicit approval
> before proceeding. Do **NOT** upload until the user confirms. This gate is
> preserved as-is from the upstream skill and must not be skipped or
> shortcut for any reason, including a prior similar confirmation earlier in
> the same session.

**Upload path for this project — Direct MCP Tool (primary):**

> **Compatibility note:** the upstream skill's "Option A" (an
> `upload_to_stitch.py` script that base64-encodes the file and POSTs to
> `/v1/projects/{projectId}/screens:batchCreate`, bypassing output token
> limits) was **not available to port** — its script content was never
> sourced. This project uses **Option B** as the primary path instead: for a
> single project's `DESIGN.md` (realistically well under ~5KB), call the
> `stitch_upload_design_md` MCP tool directly with the base64-encoded
> content. If a future `.stitch/DESIGN.md` grows large enough to hit output
> token limits with this direct approach, the Option A script would need to
> be sourced and ported before this skill can handle that case — flag it
> rather than attempting a workaround.

1. Base64-encode the contents of `.stitch/DESIGN.md`.
2. Call `stitch_upload_design_md` with the `projectId` and the base64-encoded
   content as `designMdBase64`.
3. This returns the `sourceScreen` ID and the `screenInstance` ID.
4. Call `stitch_create_design_system_from_design_md` immediately after,
   passing the `projectId` and the `selectedScreenInstance` (containing the
   `id` and `sourceScreen` returned from the upload step).

Once the upload and `stitch_create_design_system_from_design_md` have both
completed, Stitch holds the design tokens at the project level — you do NOT
need to repeat them in generation prompts (see the `generate-design` skill's
"No theme leakage" rule).

## 🎨 Apply Design System to Screens

Use `stitch_apply_design_system` to apply a design system to existing
screens.

> **Important:** `selectedScreenInstances` must contain **only** `id` and
> `sourceScreen` — do NOT include position/dimension fields (`x`, `y`,
> `width`, `height`) or the request will fail with "invalid argument". Get
> the screen instance IDs from `stitch_get_project`.

```json
{
  "projectId": "...",
  "assetId": "...",
  "selectedScreenInstances": [
    {
      "id": "...",
      "sourceScreen": "projects/.../screens/..."
    }
  ]
}
```

**How to get the required IDs:**
1. Call `stitch_get_project` to retrieve `screenInstances` — each has an `id`
   and `sourceScreen`.
2. Call `stitch_list_design_systems` to retrieve the design system `name`
   (format: `assets/{assetId}`) — use the part after `assets/` as the
   `assetId`.
3. Filter out any instances with `type: "DESIGN_SYSTEM_INSTANCE"` — only pass
   real screens.

## 📋 Update Project Metadata

After writing `.stitch/DESIGN.md`, also create or update
`.stitch/metadata.json` to track the `projectId`, `title`, all known screens,
and design system summary. No example metadata.json was available to port —
construct a reasonable structure (projectId, title, screens map, design
system asset ID, last-sync timestamp) consistent with what `generate-design`
and `extract-design-md` already reference, and flag the first real output for
a manual check the same way `.stitch/DESIGN.md`'s frontmatter should be
checked (see `extract-design-md`'s compatibility notes).

## 💡 Best Practices

Refer to the `design-md` skill for best practices on describing design
elements in natural, evocative language rather than raw CSS values.

## Compatibility notes (OpenCode / Mimir)

- All bare tool names (`list_projects`, `list_screens`, `get_screen`,
  `create_design_system_from_design_md`, `apply_design_system`,
  `get_project`, `list_design_systems`) replaced with confirmed real names
  using the `stitch_` prefix.
- `read_url_content` → `webfetch`.
- Upload path changed from the upstream's Option A (unported script) to
  Option B (direct `stitch_upload_design_md` MCP call) as primary — flagged
  above, not silently substituted.
- `examples/metadata.json` was not available to port — flagged above with a
  fallback instruction rather than fabricated content.
- The user-confirmation checkpoint before uploading is preserved unchanged
  from the upstream skill; this is a genuine safety gate, not boilerplate,
  and should not be relaxed in any future edit of this file.
