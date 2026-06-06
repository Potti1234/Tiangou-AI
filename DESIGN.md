# Design

## Intent

Tiangou-AI's marketing surface should feel like a Swiss technical poster for a Hong Kong grid-intelligence product: precise, red, typographic, civic, and engineered. The landing page is a product showcase, not an app dashboard. It should sell the value of PINN-estimated inertia and real-grid simulation through disciplined typography, real map/simulation imagery, and scroll-driven comparison moments.

The existing dashboard keeps a restrained product register. The landing page may use a more committed brand system while still linking into the app.

## Visual References

- Palette and typography reference: `C:\Users\lukas\Documents\Coding Projects\GridSFM\image copy.png`
- Typeface direction: Vercetti Regular by Filippos Fragkogiannis and Richard Mandona.
- Physical scene: an infrastructure investor and a grid engineer reviewing a Hong Kong blackout-stability demo on a large presentation wall, with the page language drawn from Swiss civic posters, red public signage, and disciplined energy-system diagrams.

## Color Strategy

Use a committed red-and-cream identity. Red carries Hong Kong and China symbolism, urgency, power flow, and public-infrastructure consequence. Cream gives the typography warmth and legibility. Graphite keeps the grid-analysis claim technical. Green, blue, and purple remain semantic system colors only.

### Core Palette

| Token | OKLCH | Hex | Use |
|---|---:|---:|---|
| `--tg-red` | `oklch(0.59 0.17 25)` | `#ce4748` | Dominant brand field, hero panels, Hong Kong/China signal |
| `--tg-red-deep` | `oklch(0.43 0.15 25)` | `#8d2024` | Deep text, pressed states, high-severity details |
| `--tg-red-soft` | `oklch(0.72 0.10 25)` | `#e37c7a` | Large soft fields, inactive red overlays |
| `--tg-cream` | `oklch(0.93 0.035 91)` | `#efe8d3` | Main light background, specimen panels |
| `--tg-warm-white` | `oklch(0.98 0.02 92)` | `#fff8e7` | High-contrast type on red, map labels |
| `--tg-graphite` | `oklch(0.18 0.015 70)` | `#1d1913` | Primary ink, dark map sections |
| `--tg-charcoal` | `oklch(0.28 0.015 70)` | `#3b352d` | Secondary ink, labels, captions |
| `--tg-gridline` | `oklch(0.74 0.018 85)` | `#b2aa99` | Swiss grid hairlines, dividers, map graticules |

### Semantic Palette

| Token | OKLCH | Hex | Use |
|---|---:|---:|---|
| `--tg-stable` | `oklch(0.55 0.13 151)` | `#1f8f54` | Stabilized system, protected timeline |
| `--tg-fault` | `oklch(0.43 0.15 25)` | `#8d2024` | Blackout/failure timeline |
| `--tg-data` | `oklch(0.54 0.13 232)` | `#2777b8` | Data provenance, measured inputs |
| `--tg-synthetic` | `oklch(0.56 0.11 298)` | `#7f63bd` | Synthetic/inferred assumptions |

### Usage Rules

- Hero and major section backgrounds may be drenched in `--tg-red`.
- Body copy on red uses `--tg-warm-white`; oversized display type may use `--tg-cream`.
- Cream sections must include red structural fields, black map regions, or strict grid dividers so the page does not become soft beige.
- The red is symbolic and structural. Do not use it as generic alert decoration everywhere.
- Do not use gradients for brand identity. Use flat fields, overlays, masked maps, and typographic contrast.
- Use 1px hairlines, not decorative shadows, for technical surfaces.

## Typography

### Primary Typeface

Use **Vercetti Regular** as the brand typeface for hero headlines, display numerals, section titles, and selected body copy. It has the geometric/humanist tension needed for a Swiss-style technical poster without becoming cold.

Implementation note: self-host the font from the official source before shipping. Keep the original license file with the font asset.

```css
@font-face {
  font-family: "Vercetti";
  src: url("/fonts/Vercetti-Regular.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
```

### Supporting Typeface

Use `Geist, ui-sans-serif, system-ui` for dense product UI elements, small labels, controls, and fallback text. Do not introduce a monospace family unless a real code/data table requires it.

### Type Scale

| Role | Size | Line height | Notes |
|---|---:|---:|---|
| Hero display | `clamp(4rem, 9vw, 6rem)` | `0.9` | Max 96px, no tighter than `-0.03em` tracking |
| Section display | `clamp(2.75rem, 5vw, 4.75rem)` | `0.95` | Swiss poster scale, one strong idea per fold |
| Statement | `clamp(1.75rem, 3vw, 2.75rem)` | `1.05` | Use for proof claims and demo captions |
| Body | `1rem` to `1.125rem` | `1.55` | Max width 65 to 75ch |
| Dense UI | `0.75rem` to `0.875rem` | `1.35` | Dashboard snippets, controls, provenance |

## Layout

- Landing page should begin with the actual product signal in the first viewport: Hong Kong grid, frequency split, or PINN stabilization comparison.
- Avoid a generic SaaS hero. The hero should feel like an interactive specimen: typography plus a real map/simulation visual.
- Use full-width sections, not stacked floating-card sections.
- Use Swiss grid discipline: strong vertical divisions, aligned baselines, generous margins, and large typographic blocks that lock to the grid.
- Prefer asymmetric compositions inside the grid: one dominant typographic field, one real simulation/map field, one compact proof column.
- Keep the next section visible below the first viewport on both desktop and mobile.
- Cards are allowed for repeated proof modules and demo controls only. Do not put cards inside cards.
- Avoid decorative diagonal slashes, random offsets, and loose collage. The page should feel constructed, not scattered.

## Imagery And Data Visuals

The brand imagery is the real grid model:

- Real MapLibre Hong Kong grid panels.
- Before/after blackout simulation maps.
- Frequency curves with 49.5 Hz and 49.0 Hz thresholds.
- Provenance overlays showing observed, inferred, and synthetic sources.
- Cropped product screenshots are acceptable if they reveal real state, not placeholder UI.

Do not use generic stock photos for the first landing page direction. The product's strongest visual asset is the assembled grid and PINN demo.

## Motion

Use scroll motion as product explanation, not decoration.

- Hero load: staged reveal of typography, then grid layer, then frequency trace.
- First major scroll: pinned split comparison, left side collapses, right side stabilizes.
- Use `prefers-reduced-motion` fallback with static before/after frames.
- Use transform, opacity, clip-path, and stroke-dashoffset. Avoid animating layout.
- Motion duration should feel decisive: 180 to 350ms for UI, longer scroll-tied sequences for pinned story sections.

## Components

### Marketing Navigation

Red or cream field, small number of links, one product CTA. Keep it restrained and precise.

### Hero Specimen

Large Vercetti headline, red/cream split field, real grid visual, concise proof statement, and a direct CTA into `/dynamic`.

### Split Simulation

Two large panels: uncontrolled blackout and Tiangou stabilization. This is the main product showcase component.

### Proof Sections

Use dense but readable modules:

- Real-grid ingestion.
- PINN-estimated inertia.
- Solver handoff.
- Provenance transparency.

Each proof module should show an artifact: map, curve, table slice, or simulation state.

## Copy Voice

Direct, technical, and confident. Avoid hype language. Describe what the system literally does:

- Good: "Estimate inertia from frequency dynamics."
- Good: "Run blackout stress cases on a reconstructed Hong Kong grid."
- Avoid: "Unlock next-generation grid intelligence."

## Accessibility

- Body text contrast must meet WCAG AA.
- Do not rely on red/green alone for blackout/stable states; use labels, iconography, and motion/state changes.
- Reduced motion must preserve the story with static frames.
- Map panels need textual summaries near them: scenario, outcome, minimum frequency, intervention count.
