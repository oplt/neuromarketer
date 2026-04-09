---
name: frontend-developer
description: Build or modify modern frontend code when the task involves React, Vue, Angular, Svelte, UI implementation, accessibility, responsive behavior, browser compatibility, or frontend performance optimization.
---

# Frontend Developer

Use this skill for implementation-heavy frontend tasks. Focus on shipping maintainable UI code that is accessible, responsive, and performant.

## Use this skill when
- Building or editing frontend features, pages, components, or design systems
- Translating product or design requirements into production UI
- Improving accessibility, interaction quality, browser compatibility, or Core Web Vitals
- Refactoring frontend state management, rendering paths, or bundle strategy
- Debugging client-side defects, layout issues, hydration problems, or rendering performance

## Do not use this skill when
- The task is primarily backend, infrastructure, database, or architecture strategy
- The user only wants brainstorming with no code or repo changes
- The task is mainly visual asset creation rather than product UI engineering

## Default objectives
- Preserve existing product conventions unless the user asks for a redesign
- Prefer small, reviewable patches over broad rewrites
- Keep accessibility and performance in scope by default
- Explain trade-offs when introducing complexity, dependencies, or framework-specific patterns

## Working rules
1. Start by locating the smallest relevant surface area: route, component, state store, styling layer, and tests.
2. Reuse existing patterns before introducing new abstractions.
3. Prefer semantic HTML, clear keyboard behavior, and accessible names over ARIA-heavy workarounds.
4. Keep responsive behavior mobile-first unless the existing codebase clearly uses a different convention.
5. Avoid premature micro-optimization, but fix obvious rendering waste, layout thrash, and oversized bundles.
6. Do not add new libraries unless the gain is material and the repo does not already have an equivalent.
7. Keep UI state predictable. Avoid scattering similar state across many components when a shared owner is clearer.
8. Add or update targeted tests when the repo already has frontend test coverage patterns.

## Implementation checklist
### 1) Understand the feature or defect
- Identify the affected user flow
- Find the entry point, state owner, data dependencies, and styling system
- Confirm constraints: framework version, routing model, SSR/CSR behavior, design tokens, and existing test strategy

### 2) Implement with accessibility first
- Use semantic structure before custom roles
- Ensure focus order and keyboard interaction are intentional
- Provide accessible names for controls, landmarks, form elements, dialogs, tables, and interactive regions
- Respect reduced motion and color-contrast expectations when touching animation or theme logic

### 3) Keep performance in scope
- Reduce unnecessary rerenders
- Use memoization only when it measurably helps clarity or performance
- Split code or defer non-critical work for heavy routes/components
- Optimize images, expensive effects, and large lists when relevant

### 4) Verify behavior
- Check empty, loading, error, and success states
- Check mobile, tablet, and desktop layouts if the change affects layout
- Check hover, focus, disabled, and keyboard paths for interactive elements
- Run the smallest relevant validation commands

## Output expectations
When reporting back:
- State the root cause or implementation goal in plain language
- List changed files and why each changed
- Call out any accessibility or performance considerations
- Mention tests or validation run, plus gaps if something could not be verified

## Preferred deliverable shape
Use concise sections like:
- Goal
- Findings
- Changes made
- Validation
- Risks / follow-ups

## Quality bar
A good result leaves the frontend:
- Easier to understand than before
- At least as accessible as before, ideally better
- No slower in critical paths without explicit justification
- Consistent with the repo's design and implementation patterns
