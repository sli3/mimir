---
name: taste-design
description: Semantic Design System Skill for Google Stitch. Generates agent-friendly DESIGN.md files that enforce premium, anti-generic UI standards — strict typography, calibrated color, asymmetric layouts, perpetual micro-motion, and hardware-accelerated performance.
allowed-tools:
  - "stitch_*"
  - "read"
  - "write"
---

# Stitch Design Taste — Semantic Design System Skill

## ⚠️ Mimir precedence note — read before using

This skill is **secondary and optional**, not a replacement for
`extract-design-md`. It prescribes a specific, opinionated aesthetic with
hard bans that may directly conflict with Mimir's real, existing design —
most notably:

- **Bans the `Inter` font** — a common dashboard font choice. If Mimir's
  actual `dashboard/frontend/` uses Inter, `extract-design-md`'s output (the
  real font in use) takes precedence. Do not let this skill override a real,
  working font choice just because it appears on the ban list.
- **Bans pure black (`#000000`)** — Mimir's dashboard is described in its own
  backend docstring as "the cyberpunk React dashboard," which plausibly uses
  pure/near-pure black. Same rule: reality from `extract-design-md` wins over
  this skill's stylistic preference.
- General bias toward marketing-site/SaaS conventions (asymmetric hero
  sections, perpetual micro-motion, card-elevation minimalism) that may not
  suit a data-dense RF instrument panel, where legibility and clear data
  grouping matter more than some of this skill's aesthetic preferences (e.g.
  "replace cards with border-top dividers" could hurt a panel that needs
  visually distinct data groupings).

**Conflict-resolution rule for this project:** when this skill's guidance
contradicts what `extract-design-md` found in Mimir's real source code, the
extracted reality wins. Use this skill only for genuinely new decisions where
Mimir's existing code doesn't already have an answer (e.g. a brand-new panel
type with no precedent in the current dashboard) — not to override existing,
working design choices.

## Overview
This skill generates `DESIGN.md` files optimized for Google Stitch screen generation. It translates a set of anti-slop frontend engineering directives into Stitch's native semantic design language — descriptive, natural-language rules paired with precise values that Stitch's AI agent can interpret to produce premium, non-generic interfaces.

The generated `DESIGN.md` serves as a source of truth for prompting Stitch to generate new screens that align with a curated, high-agency design language. Stitch interprets design through **"Visual Descriptions"** supported by specific color values, typography specs, and component behaviors.

## Prerequisites
- Access to the Stitch MCP Server (confirmed connected — `stitch_*` tools)

## The Goal
Generate a `DESIGN.md` file that encodes:
1. **Visual atmosphere** — the mood, density, and design philosophy
2. **Color calibration** — neutrals, accents, and banned patterns with hex codes
3. **Typographic architecture** — font stacks, scale hierarchy, and anti-patterns
4. **Component behaviors** — buttons, cards, inputs with interaction states
5. **Layout principles** — grid systems, spacing philosophy, responsive strategy
6. **Motion philosophy** — animation engine specs, spring physics, perpetual micro-interactions
7. **Anti-patterns** — explicit list of banned AI design clichés

## Analysis & Synthesis Instructions

### 1. Define the Atmosphere
Evaluate the target project's intent. Use evocative adjectives from the taste spectrum:
- **Density:** "Art Gallery Airy" (1–3) → "Daily App Balanced" (4–7) → "Cockpit Dense" (8–10)
- **Variance:** "Predictable Symmetric" (1–3) → "Offset Asymmetric" (4–7) → "Artsy Chaotic" (8–10)
- **Motion:** "Static Restrained" (1–3) → "Fluid CSS" (4–7) → "Cinematic Choreography" (8–10)

Default baseline: Creativity 9, Variance 8, Motion 6, Density 5. For Mimir
specifically, consider whether a live RF instrument panel actually wants
Density 5 / Variance 8 — a data-dense scanning tool may legitimately want
higher density and lower variance than this skill's default, since
"cockpit dense" is a real, valid choice for instrumentation, not a fallback
to avoid.

### 2. Map the Color Palette
For each color provide: **Descriptive Name** + **Hex Code** + **Functional Role**.

**Mandatory constraints:**
- Maximum 1 accent color. Saturation below 80%
- The "AI Purple/Blue Neon" aesthetic is strictly BANNED — no purple button glows, no neon gradients
- Use absolute neutral bases (Zinc/Slate) with high-contrast singular accents
- Stick to one palette for the entire output — no warm/cool gray fluctuation
- Never use pure black (`#000000`) — use Off-Black, Zinc-950, or Charcoal
  (see Mimir precedence note above — verify against the real extracted
  palette first)

### 3. Establish Typography Rules
- **Display/Headlines:** Track-tight, controlled scale. Not screaming. Hierarchy through weight and color, not just massive size
- **Body:** Relaxed leading, max 65 characters per line
- **Font Selection:** `Inter` is BANNED for premium/creative contexts (see
  Mimir precedence note above). Force unique character: `Geist`, `Outfit`,
  `Cabinet Grotesk`, or `Satoshi`
- **Serif Ban:** Generic serif fonts (`Times New Roman`, `Georgia`, `Garamond`, `Palatino`) are BANNED. If serif is needed for editorial/creative contexts, use only distinctive modern serifs: `Fraunces`, `Gambarino`, `Editorial New`, or `Instrument Serif`. Serif is always BANNED in dashboards or software UIs
- **Dashboard Constraint:** Use Sans-Serif pairings exclusively (`Geist` + `Geist Mono` or `Satoshi` + `JetBrains Mono`)
- **High-Density Override:** When density exceeds 7, all numbers must use Monospace — relevant for Mimir's numeric-heavy panels (SNR, frequency, peak power readouts)

### 4. Define the Hero Section
Most Mimir pages are instrument panels, not marketing pages — this section
likely does not apply. Skip it for dashboard/instrumentation screens; only
consider it if generating a genuinely new landing/marketing-style page (e.g.
a project README-style splash page, if one is ever wanted).

### 5. Describe Component Stylings
For each component type, describe shape, color, shadow depth, and interaction behavior:
- **Buttons:** Tactile push feedback on active state. No neon outer glows. No custom mouse cursors
- **Cards:** Use ONLY when elevation communicates hierarchy. Tint shadows to background hue. For high-density layouts, replace cards with border-top dividers or negative space — weigh this against Mimir's need for visually distinct data groupings (waterfall panel, AI Reasoning panel, ADS-B table) before applying
- **Inputs/Forms:** Label above input, helper text optional, error text below. Standard gap spacing
- **Loading States:** Skeletal loaders matching layout dimensions — no generic circular spinners
- **Empty States:** Composed compositions indicating how to populate data — relevant for the `/vectordb` page's pre-seed empty state (`status: "empty"` from `/api/vectorstore/points`)
- **Error States:** Clear, inline error reporting

### 6. Define Layout Principles
- No overlapping elements — every element occupies its own clear spatial zone. No absolute-positioned content stacking
- Centered Hero sections are BANNED when variance exceeds 4 — not applicable to instrument panels (see Section 4)
- The generic "3 equal cards horizontally" feature row is BANNED — use 2-column Zig-Zag, asymmetric grid, or horizontal scroll (again, weigh against dashboard legibility needs)
- CSS Grid over Flexbox math — never use `calc()` percentage hacks
- Contain layouts using max-width constraints (e.g., 1400px centered)
- Full-height sections must use `min-h-[100dvh]` — never `h-screen` (iOS Safari catastrophic jump)

### 7. Define Responsive Rules
Every design must work across all viewports:
- **Mobile-First Collapse (< 768px):** All multi-column layouts collapse to single column. No exceptions
- **No Horizontal Scroll:** Horizontal overflow on mobile is a critical failure
- **Typography Scaling:** Headlines scale via `clamp()`. Body text minimum `1rem`/`14px`
- **Touch Targets:** All interactive elements minimum `44px` tap target
- **Navigation:** Desktop horizontal nav collapses to clean mobile menu
- **Spacing:** Vertical section gaps reduce proportionally (`clamp(3rem, 8vw, 6rem)`)

### 8. Encode Motion Philosophy
- **Spring Physics default:** `stiffness: 100, damping: 20` — premium, weighty feel. No linear easing
- **Perpetual Micro-Interactions:** Every active component should have an infinite loop state (Pulse, Typewriter, Float, Shimmer) — consider carefully for Mimir: a live waterfall already has continuous real motion from actual data; additional decorative micro-motion on static UI chrome may compete with or distract from the real-data motion that matters
- **Staggered Orchestration:** Never mount lists instantly — use cascade delays for waterfall reveals (note: "waterfall" here is a generic UI term for list-reveal animation, not Mimir's RF waterfall display — don't conflate the two)
- **Performance:** Animate exclusively via `transform` and `opacity`. Never animate `top`, `left`, `width`, `height`. Grain/noise filters on fixed pseudo-elements only

### 9. List Anti-Patterns (AI Tells)
Encode these as explicit "NEVER DO" rules in the DESIGN.md:
- No emojis anywhere
- No `Inter` font (see Mimir precedence note)
- No generic serif fonts (`Times New Roman`, `Georgia`, `Garamond`) — distinctive modern serifs only if needed
- No pure black (`#000000`) (see Mimir precedence note)
- No neon/outer glow shadows
- No oversaturated accents
- No excessive gradient text on large headers
- No custom mouse cursors
- No overlapping elements — clean spatial separation always
- No 3-column equal card layouts
- No generic names ("John Doe", "Acme", "Nexus")
- No fake round numbers (`99.99%`, `50%`)
- No fabricated data or statistics — never generate metrics, performance numbers, uptime percentages, response times, or any data that wasn't explicitly provided. This is especially important for Mimir: never invent plausible-looking SNR values, confidence percentages, or calibration numbers. If real data isn't available, use a clear placeholder label like `[metric]`.
- No fake system/metric sections — dashboard cards filled with invented data are BANNED. Directly relevant to Mimir, which has already had a real bug (Phase 32, Confidence Provenance Gating) caused by displaying confidence values without clear grounding in real signal presence.
- No `LABEL // YEAR` formatting
- No AI copywriting clichés ("Elevate", "Seamless", "Unleash", "Next-Gen")
- No filler UI text: "Scroll to explore", "Swipe down", scroll arrows, bouncing chevrons
- No broken Unsplash links — use `picsum.photos` or SVG avatars
- No centered Hero sections (not applicable to instrument panels)

## Output Format (DESIGN.md Structure)

```markdown
# Design System: [Project Title]

## 1. Visual Theme & Atmosphere
(Evocative description of the mood, density, variance, and motion intensity.)

## 2. Color Palette & Roles
- **[Descriptive Name]** (#XXXXXX) — Functional role
(Max 1 accent. Saturation < 80%. No purple/neon. Verify against
extract-design-md's real findings before finalizing.)

## 3. Typography Rules
- **Display:** [Font Name]
- **Body:** [Font Name]
- **Mono:** [Font Name] — for numeric-heavy panels
- **Banned:** Inter, generic system fonts for premium contexts (unless
  extract-design-md found Inter already in real use — see precedence note)

## 4. Component Stylings
* **Buttons:** ...
* **Cards:** ...
* **Inputs:** ...
* **Loaders:** ...
* **Empty States:** ...

## 5. Layout Principles
(...)

## 6. Motion & Interaction
(...)

## 7. Anti-Patterns (Banned)
(...)
```

## Best Practices
- **Be Descriptive:** "Deep Charcoal Ink (#18181B)" — not just "dark text"
- **Be Functional:** Explain what each element is used for
- **Be Consistent:** Same terminology throughout the document
- **Be Precise:** Include exact hex codes, rem values, pixel values in parentheses
- **Be Opinionated, but not blindly** — this skill is not a neutral template;
  it enforces a specific aesthetic. For Mimir, that aesthetic is subordinate
  to what `extract-design-md` finds in the real codebase (see precedence
  note at the top of this file).

## Tips for Success
1. Start with the atmosphere — understand the vibe before detailing tokens
2. Look for patterns — identify consistent spacing, sizing, and styling
3. Think semantically — name colors by purpose, not just appearance
4. Consider hierarchy — document how visual weight communicates importance
5. Encode the bans — anti-patterns are as important as the rules themselves,
   but check each one against Mimir's real design first

## Common Pitfalls to Avoid
- Using technical jargon without translation
- Omitting hex codes or using only descriptive names
- Forgetting functional roles of design elements
- Being too vague in atmosphere descriptions
- Applying this skill's bans over real, working design choices found by
  `extract-design-md` — this is the most important pitfall for this project
  specifically

## Compatibility notes (OpenCode / Mimir)

- `allowed-tools` changed from `StitchMCP`/`Read`/`Write` to
  `stitch_*`/`read`/`write` for OpenCode naming convention. This skill makes
  no direct MCP tool calls in its body (same shape as `enhance-prompt`), so
  no call-syntax translation was needed.
- Added the precedence note at the top of this file and inline flags
  throughout — this is the most opinionated skill ported so far, and its
  hard bans (Inter, pure black) are plausible direct conflicts with Mimir's
  actual existing design. `extract-design-md`'s findings should always take
  priority over this skill's preferences when the two disagree.
- Removed the Hero Section guidance's applicability by default (Section 4)
  since Mimir's pages are instrument panels, not marketing pages — flagged
  as skip-unless-relevant rather than deleted outright, in case a genuine
  marketing/splash page is ever wanted.
