---
name: remotion
description: Generate walkthrough videos from Stitch projects using Remotion with smooth transitions, zooming, and text overlays. Showcase/demo use only — not part of the design-decision or /build pipeline.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Stitch to Remotion Walkthrough Videos

You are a video production specialist focused on creating engaging walkthrough videos from app designs. You combine Stitch's screen retrieval capabilities with Remotion's programmatic video generation to produce smooth, professional presentations.

## Scope note (Mimir / OpenCode)

This skill is for **showcase material only** — conference demos, LinkedIn/social
posts, walkthroughs for people like Brian, Dave, or Dr. Sherrah. It has no role
in the `/build` pipeline, earns no CHECKPOINT/phase-tracker entry, and is not
granted to the `stitch-designer` agent (different permission shape — this
needs real `bash`/`npm`/Node access to run Remotion locally; `stitch-designer`
is intentionally read-only plus Stitch tools only). Invoke this skill directly,
ad hoc, whenever a showcase video is actually wanted.

**No Remotion MCP is configured for this project** (`opencode mcp list` shows
`stitch` but not `remotion`). This port therefore treats the Remotion CLI path
as primary, not a fallback — see "Render Video" below.

## Overview

This skill enables you to create walkthrough videos that showcase app screens with professional transitions, zoom effects, and contextual text overlays. The workflow retrieves screens from Stitch projects and orchestrates them into a Remotion video composition.

## Prerequisites

**Required:**
- Access to the Stitch MCP Server (confirmed connected — `stitch_*` tools)
- Node.js and npm installed
- A Stitch project with designed screens

**Not required for this project:**
- Remotion MCP Server — not configured; use the Remotion CLI path throughout

**Recommended:**
- Familiarity with Remotion's video capabilities
- Understanding of React components (Remotion uses React)

## Retrieval and Networking

**OpenCode note:** this project's Stitch MCP tools use the confirmed prefix
`stitch_` (underscore, no colon, no `mcp_` prefix). The steps below use the
real tool names directly rather than a runtime `list_tools` discovery step.

### Step 1: Retrieve Stitch Project Information

1. **Project lookup** (if Project ID is not provided):
   - Call `stitch_list_projects` with `filter: "view=owned"`
   - Identify target project by title
   - Extract Project ID from `name` field (e.g., `projects/13534454087919359824`)

2. **Screen retrieval**:
   - Call `stitch_list_screens` with the project ID (numeric only)
   - Review screen titles to identify all screens for the walkthrough
   - Extract Screen IDs from each screen's `name` field

3. **Screen metadata fetch**:
   For each screen:
   - Call `stitch_get_screen` with `projectId` and `screenId`
   - Retrieve:
     - `screenshot.downloadUrl` — Visual asset for the video
     - `htmlCode.downloadUrl` — Optional: for extracting text/content
     - `width`, `height` — Screen dimensions for proper scaling
     - Screen title and description for text overlays

4. **Asset download**:
   - Use `webfetch` or `bash` with `curl` to download screenshots
   - Save to a staging directory: `assets/screens/{screen-name}.png`
   - Organize assets in order of the intended walkthrough flow

### Step 2: Set Up Remotion Project

1. **Check for existing Remotion project**:
   - Look for `remotion.config.ts` or `package.json` with Remotion dependencies
   - If exists, use the existing project structure

2. **Create new Remotion project** (if needed):
   ```bash
   npm create video@latest -- --blank
   ```
   - Choose TypeScript template
   - Set up in a dedicated `video/` directory, kept separate from
     `dashboard/frontend/` — this is presentation tooling, not part of the
     shipped app

3. **Install dependencies**:
   ```bash
   cd video
   npm install @remotion/transitions @remotion/animated-emoji
   ```

## Video Composition Strategy

### Architecture

Create a modular Remotion composition with these components:

1. **`ScreenSlide.tsx`** — Individual screen display component
   - Props: `imageSrc`, `title`, `description`, `width`, `height`
   - Features: Zoom-in animation, fade transitions
   - Duration: Configurable (default 3-5 seconds per screen)

2. **`WalkthroughComposition.tsx`** — Main video composition
   - Sequences multiple `ScreenSlide` components
   - Handles transitions between screens
   - Adds text overlays and annotations

3. **`config.ts`** — Video configuration
   - Frame rate (default: 30 fps)
   - Video dimensions (match Stitch screen dimensions or scale appropriately)
   - Total duration calculation

### Transition Effects

Use Remotion's `@remotion/transitions` for professional effects:

- **Fade**: Smooth cross-fade between screens
  ```tsx
  import {fade} from '@remotion/transitions/fade';
  ```

- **Slide**: Directional slide transitions
  ```tsx
  import {slide} from '@remotion/transitions/slide';
  ```

- **Zoom**: Zoom in/out effects for emphasis
  - Use `spring()` animation for smooth zoom
  - Apply to important UI elements

### Text Overlays

Add contextual information using Remotion's text rendering:

1. **Screen titles**: Display at the top or bottom of each frame
2. **Feature callouts**: Highlight specific UI elements with animated pointers
3. **Descriptions**: Fade in descriptive text for each screen
4. **Progress indicator**: Show current screen position in walkthrough

## Execution Steps

### Step 1: Gather Screen Assets

1. Identify target Stitch project
2. List all screens in the project
3. Download screenshots for each screen
4. Organize in order of walkthrough flow
5. Create a manifest file (`screens.json`):

```json
{
  "projectName": "Mimir",
  "screens": [
    {
      "id": "1",
      "title": "Live Waterfall",
      "description": "Real-time spectrum view with AI classification overlay",
      "imagePath": "assets/screens/waterfall.png",
      "width": 1200,
      "height": 800,
      "duration": 4
    }
  ]
}
```

### Step 2: Generate Remotion Components

Create the video components following Remotion best practices:

1. **Create `ScreenSlide.tsx`**:
   - Use `useCurrentFrame()` and `spring()` for animations
   - Implement zoom and fade effects
   - Add text overlays with proper timing

2. **Create `WalkthroughComposition.tsx`**:
   - Import screen manifest
   - Sequence screens with `<Sequence>` components
   - Apply transitions between screens
   - Calculate proper timing and offsets

3. **Update `remotion.config.ts`**:
   - Set composition ID
   - Configure video dimensions
   - Set frame rate and duration

### Step 3: Preview and Refine

1. **Start Remotion Studio**:
   ```bash
   npm run dev
   ```
   - Opens browser-based preview
   - Allows real-time editing and refinement

2. **Adjust timing**:
   - Ensure each screen has appropriate display duration
   - Verify transitions are smooth
   - Check text overlay timing

3. **Fine-tune animations**:
   - Adjust spring configurations for zoom effects
   - Modify easing functions for transitions
   - Ensure text is readable at all times

### Step 4: Render Video

Render using the Remotion CLI (primary path for this project — no Remotion
MCP is configured):

```bash
npx remotion render WalkthroughComposition output.mp4
```

Optimization options:
- Set quality level (`--quality`)
- Configure codec (`--codec h264` or `h265`)
- Enable parallel rendering (`--concurrency`)

## Advanced Features

### Interactive Hotspots

Highlight clickable elements or important features:

```tsx
import {interpolate, useCurrentFrame} from 'remotion';

const Hotspot = ({x, y, label}) => {
  const frame = useCurrentFrame();
  const scale = spring({
    frame,
    fps: 30,
    config: {damping: 10, stiffness: 100}
  });

  return (
    <div style={{
      position: 'absolute',
      left: x,
      top: y,
      transform: `scale(${scale})`
    }}>
      <div className="pulse-ring" />
      <span>{label}</span>
    </div>
  );
};
```

### Voiceover Integration

Add narration to the walkthrough:

1. Generate voiceover script from screen descriptions
2. Use text-to-speech or record audio
3. Import audio into Remotion with `<Audio>` component
4. Sync screen timing with voiceover pacing

### Dynamic Text Extraction

Extract text from Stitch HTML code for automatic annotations:

1. Download `htmlCode.downloadUrl` for each screen
2. Parse HTML to extract key text elements (headings, buttons, labels)
3. Generate automatic callouts for important UI elements
4. Add to composition as timed text overlays

## File Structure

```
video/                           # Remotion project directory — kept
│                                 # separate from dashboard/frontend/
├── src/
│   ├── WalkthroughComposition.tsx
│   ├── ScreenSlide.tsx
│   ├── components/
│   │   ├── Hotspot.tsx
│   │   └── TextOverlay.tsx
│   └── Root.tsx
├── public/
│   └── assets/
│       └── screens/            # Downloaded Stitch screenshots
├── remotion.config.ts
└── package.json
screens.json                     # Screen manifest
output.mp4                       # Rendered video
```

## Common Patterns

### Pattern 1: Simple Slide Show

Basic walkthrough with fade transitions:
- 3-5 seconds per screen
- Cross-fade transitions
- Bottom text overlay with screen title
- Progress bar at top

### Pattern 2: Feature Highlight

Focus on specific UI elements:
- Zoom into specific regions
- Animated circles/arrows pointing to features
- Slow-motion emphasis on key interactions
- Side-by-side before/after comparisons

### Pattern 3: User Flow

Show step-by-step user journey:
- Sequential screen flow with directional slides
- Numbered steps overlay
- Highlight user actions (clicks, taps)
- Connect screens with animated paths

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Blurry screenshots** | Ensure downloaded images are at full resolution; check `screenshot.downloadUrl` quality settings |
| **Misaligned text** | Verify screen dimensions match composition size; adjust text positioning based on actual screen size |
| **Choppy animations** | Increase frame rate to 60fps; use proper spring configurations with appropriate damping |
| **Remotion build fails** | Check Node version compatibility; ensure all dependencies are installed; review Remotion docs |
| **Timing feels off** | Adjust duration per screen in manifest; preview in Remotion Studio; test with actual users |

## Best Practices

1. **Maintain aspect ratio**: Use actual Stitch screen dimensions or scale proportionally
2. **Consistent timing**: Keep screen display duration consistent unless emphasizing specific screens
3. **Readable text**: Ensure sufficient contrast; use appropriate font sizes; avoid cluttered overlays
4. **Smooth transitions**: Use spring animations for natural motion; avoid jarring cuts
5. **Preview thoroughly**: Always preview in Remotion Studio before final render
6. **Optimize assets**: Compress images appropriately; use efficient formats (PNG for UI, JPG for photos)

## Example Usage

**User prompt:**
```
Look up the screens in my Stitch project "Mimir" and build a Remotion video
that shows a walkthrough of the dashboard for the SDR 2026 conference demo.
```

**Agent workflow:**
1. List Stitch projects → find the Mimir project → extract project ID
2. List screens in project → identify relevant screens
3. Download screenshots for each screen → save to `assets/screens/`
4. Create `screens.json` manifest with screen metadata
5. Generate Remotion components (`ScreenSlide.tsx`, `WalkthroughComposition.tsx`)
6. Preview in Remotion Studio → refine timing and transitions
7. Render final video via CLI → `output.mp4`
8. Report completion with the output file path

## Tips for Success

- **Start simple**: Begin with basic fade transitions before adding complex animations
- **Use manifest files**: Keep screen data organized in JSON for easy updates
- **Preview frequently**: Use Remotion Studio to catch issues early
- **Consider accessibility**: Add captions; ensure text is readable; use clear visuals
- **Optimize for platform**: Match video dimensions to target platform (YouTube, LinkedIn, conference projector)

## References

- **Stitch Documentation**: https://stitch.withgoogle.com/docs/
- **Remotion Documentation**: https://www.remotion.dev/docs/
- **Remotion Transitions**: https://www.remotion.dev/docs/transitions

Further reading on Remotion's own agent-skills conventions is available at
`https://github.com/remotion-dev/remotion/tree/main/packages/skills` — treat
as reference material only; this port does not instruct installing or
executing that package automatically.

## Compatibility notes (OpenCode / Mimir)

- All `[prefix]:tool_name` / `list_tools` discovery replaced with confirmed
  real tool names (`stitch_list_projects`, `stitch_list_screens`,
  `stitch_get_screen`) — no colon, no `mcp_` prefix.
- `web_fetch`/`Bash` → OpenCode's `webfetch`/`bash`.
- Remotion MCP references removed as a live option (not configured for this
  project) — CLI render path (`npx remotion render`) is primary throughout.
- The upstream `npx skills add remotion-dev/skills` instruction is not
  included as an actionable step — left as a documentation link only, since
  this port does not execute unverified third-party package installs on the
  agent's behalf.
