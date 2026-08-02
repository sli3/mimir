# DESIGN.md Format — Condensed Spec Reference

Source: `google-labs-code/design.md` (Apache 2.0). Stitch-compatible.

## Frontmatter (YAML, top of file)

Top-level keys:

- `version` (optional string, e.g. `"alpha"`)
- `name` (required string) — human-readable design system name
- `description` (optional string) — short summary
- `omitted` (optional array of section names) — sections intentionally
  skipped from the body. Use this when a section is genuinely not
  applicable, NOT to silently drop sections.
- `colors` — map of token-name → CSS color value. Any valid CSS color
  string (hex, named, rgb(), hsl(), oklch(), etc). Hex recommended as
  default. Custom/domain-specific token names (e.g. `neon-cyan`,
  `bg-root`, `wf-noise`) are spec-compliant — the spec's "Consumer
  Behavior for Unknown Content" rule accepts unknown color/typography
  token names as long as the value itself is valid. Do not rename
  existing domain-specific tokens to match Material Design naming.
- `typography` — map of token-name → object with:
  - `fontFamily` (string)
  - `fontSize` (Dimension: `px`, `em`, or `rem`)
  - `fontWeight` (number)
  - `lineHeight` (Dimension OR unitless number multiplier of fontSize)
  - `letterSpacing` (optional Dimension)
  - `fontFeature` (optional)
  - `fontVariation` (optional)
- `rounded` — map of scale-level (`sm`/`md`/`lg`/`xl`/`full` or
  custom) → Dimension
- `spacing` — map of scale-level → Dimension or unitless number
- `components` — map of component-name → map of property → value.
  Values may be literals OR `{path.to.token}` references to other
  frontmatter values (e.g. `backgroundColor: "{colors.bg-panel}"`,
  `typography: "{typography.body}"`).
  Common component properties: `backgroundColor`, `textColor`,
  `typography`, `rounded`, `padding`, `size`, `height`, `width`.
  Variants get their own key (e.g. `button-primary` + `button-primary-hover`).

### Known spec gap: text-transform

Google's DESIGN.md typography token schema (`fontFamily`, `fontSize`,
`fontWeight`, `lineHeight`, `letterSpacing`, `fontFeature`,
`fontVariation`) has NO property for `text-transform` (uppercase /
lowercase / capitalize). If a design uses uppercase labels or similar
treatment, describe this in the markdown body's **Typography** section
prose — do NOT add a `textTransform` key to a frontmatter typography
token, as the linter will flag it as an unrecognised property every
time. This is a genuine limitation in the current DESIGN.md spec
(confirmed against `docs/spec.md`), not an extraction mistake.

## Body Section Order

`##` headings, in this exact order. Present sections must follow it.
Sections may be omitted only if declared in the frontmatter `omitted`
list — do not silently drop.

| ## Heading (body)             | `omitted:` canonical value |
|-------------------------------|----------------------------|
| Overview (aka "Brand & Style")| `Overview`                 |
| Colors                        | `Colors`                   |
| Typography                    | `Typography`               |
| Layout (aka "Layout & Spacing")| `Layout`                  |
| Elevation & Depth (aka "Elevation")| `Elevation`            |
| Shapes                        | `Shapes`                   |
| Components                    | `Components`               |
| Do's and Don'ts               | `Do's and Don'ts`          |

**Note on the `omitted:` list:** when declaring a section in the
`omitted:` frontmatter list, use the EXACT string from the right-hand
column — the `@google/design.md` lint command checks against these
canonical short names specifically, not the longer "aka" heading
variants shown in the left-hand column. The shorter form on the right
is the value the linter's `unknown-omission` rule validates against.

**Confirmation status of the canonical names above:** only `Elevation`
has been independently confirmed against a real lint run
(`unknown-omission: unknown section name 'Elevation & Depth' in
omitted key` — the linter suggested `Elevation`). The other seven
follow the same de-aka'd pattern and should be treated as the best
current guess, not a guarantee, until each is independently confirmed
by a future lint run. If a future DESIGN.md triggers
`unknown-omission` for one of the other seven names, treat that lint
message as authoritative and update this table.

## Frontmatter Minimum

The frontmatter MUST include `colors`, AND SHOULD include
`typography`, `rounded`, `spacing`, and `components` sections if the
analysed codebase has enough information to populate them meaningfully.
Do not default to a name+colors-only frontmatter.

## Expected Linter Warnings for Non-Generic Design Systems

The linter's `missing-primary` and `orphaned-tokens` rules assume a
generic single-primary-colour, fully-componentized design system.

A design system that legitimately uses multiple co-equal semantic
accent colours (e.g. distinct colours for success / warning / info /
danger states rather than one dominant "primary") will trigger
`missing-primary`, and a design system that documents a broader
colour / token vocabulary than what's currently wired into formal
component definitions will trigger `orphaned-tokens` for every token
not yet referenced by a `components:` entry.

**THESE ARE NOT BUGS TO FIX BY INVENTING VALUES.** Do not add a fake
`primary:` alias or pad out `components:` with entries not grounded in
real, observed UI just to silence these warnings — that would mean
writing false information into the DESIGN.md. If genuinely
appropriate for a specific project, note in the DESIGN.md's own prose
why these warnings are expected and move on.
