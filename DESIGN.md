# NEO MIRAI AI Design Conference

## Mission
Create implementation-ready, token-driven UI guidance for NEO MIRAI AI Design Conference that is optimized for consistency, accessibility, and fast delivery across content site.

## Brand
- Product/brand: NEO MIRAI AI Design Conference
- URL: https://impeccable.style/neo-mirai/
- Audience: readers and knowledge seekers
- Product surface: content site

## Style Foundations
- Visual style: clean, functional, implementation-oriented
- Main font style: `font.family.primary=Zen Old Mincho`, `font.family.stack=Zen Old Mincho, Hiragino Mincho ProN, serif`, `font.size.base=16px`, `font.weight.base=400`, `font.lineHeight.base=24.8px`
- Typography scale: `font.size.xs=8.32px`, `font.size.sm=9.92px`, `font.size.md=10.24px`, `font.size.lg=10.88px`, `font.size.xl=11.2px`, `font.size.2xl=11.52px`, `font.size.3xl=12.48px`, `font.size.4xl=12.6px`
- Color palette: `color.text.primary=oklch(0.18 0.035 82)`, `color.text.secondary=oklch(0.32 0.045 80)`, `color.text.tertiary=oklch(0.97 0.02 82)`, `color.text.inverse=oklch(0.76 0.165 80)`, `color.surface.base=#000000`, `color.surface.muted=oklch(0.91 0.045 78)`, `color.surface.strong=oklch(0.94 0.035 78)`
- Spacing scale: `space.1=0.64px`, `space.2=3.84px`, `space.3=6.08px`, `space.4=8px`, `space.5=8.96px`, `space.6=9.28px`, `space.7=10.4px`, `space.8=11.2px`
- Radius/shadow/motion tokens: `radius.xs=50px` | `shadow.1=lab(5.25975 2.88012 6.66661 / 0.08) 0px 18px 50px 0px` | `motion.duration.instant=180ms`, `motion.duration.fast=240ms`, `motion.duration.normal=480ms`, `motion.duration.slow=560ms`, `motion.duration.slower=700ms`

## Accessibility
- Target: WCAG 2.2 AA
- Keyboard-first interactions required.
- Focus-visible rules required.
- Contrast constraints required.

## Writing Tone
Concise, confident, implementation-focused.

## Rules: Do
- Use semantic tokens, not raw hex values, in component guidance.
- Every component must define states for default, hover, focus-visible, active, disabled, loading, and error.
- Component behavior should specify responsive and edge-case handling.
- Interactive components must document keyboard, pointer, and touch behavior.
- Accessibility acceptance criteria must be testable in implementation.

## Rules: Don't
- Do not allow low-contrast text or hidden focus indicators.
- Do not introduce one-off spacing or typography exceptions.
- Do not use ambiguous labels or non-descriptive actions.
- Do not ship component guidance without explicit state rules.

## Guideline Authoring Workflow
1. Restate design intent in one sentence.
2. Define foundations and semantic tokens.
3. Define component anatomy, variants, interactions, and state behavior.
4. Add accessibility acceptance criteria with pass/fail checks.
5. Add anti-patterns, migration notes, and edge-case handling.
6. End with a QA checklist.

## Required Output Structure
- Context and goals.
- Design tokens and foundations.
- Component-level rules (anatomy, variants, states, responsive behavior).
- Accessibility requirements and testable acceptance criteria.
- Content and tone standards with examples.
- Anti-patterns and prohibited implementations.
- QA checklist.

## Component Rule Expectations
- Include keyboard, pointer, and touch behavior.
- Include spacing and typography token requirements.
- Include long-content, overflow, and empty-state handling.
- Include known page component density: links (26), cards (11), buttons (5), lists (5), navigation (3).


## Quality Gates
- Every non-negotiable rule must use "must".
- Every recommendation should use "should".
- Every accessibility rule must be testable in implementation.
- Teams should prefer system consistency over local visual exceptions.
