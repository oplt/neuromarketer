---
name: senior-fullstack-web
description: Implement premium full-stack web features when the task involves Laravel, Livewire, FluxUI, advanced CSS, animation polish, or selective Three.js usage for production web experiences.
---

# Senior Full-Stack Web

Use this skill for implementation tasks that need strong product polish, solid engineering discipline, and high-quality Laravel/Livewire frontend integration.

## Use this skill when
- Building or modifying Laravel or Livewire features
- Working with FluxUI components or adjacent Blade/UI patterns
- Adding premium interaction design, advanced CSS, theming, or tasteful motion
- Evaluating whether enhanced presentation techniques such as Three.js are justified

## Do not use this skill when
- The task is purely architecture strategy with no implementation
- The task is mostly infrastructure, data engineering, or backend systems work unrelated to the web product
- The request is for flashy effects that would materially harm maintainability, accessibility, or performance

## Default stance
- Premium does not mean heavy
- Visual sophistication must coexist with responsiveness, accessibility, and maintainability
- Preserve the product specification; do not invent net-new features unless requested
- Prefer the simplest implementation that achieves the intended level of polish

## Working rules
1. Read the requested scope carefully and implement only what is needed.
2. Respect existing Laravel, Livewire, Blade, and component conventions in the repo.
3. Do not install Alpine separately when Livewire already provides the needed behavior through the existing stack.
4. Treat advanced visual effects as optional enhancements, not defaults.
5. Theme support must remain coherent across light, dark, and system modes when the product already supports them.
6. Motion should feel deliberate and fast; avoid gimmicks and avoid blocking interactions.
7. Three.js is justified only when it materially improves the experience and the performance budget can support it.
8. Keep server-rendered and reactive boundaries clear to avoid brittle component state.

## Implementation process
### 1) Scope the change
- Identify controller, route, Livewire component, Blade view, style layer, and data dependencies
- Clarify whether the change is structural, stylistic, or both
- Confirm whether existing patterns or components already solve most of the task

### 2) Implement the base experience first
- Build the core feature in a stable, accessible form
- Ensure forms, validation, loading, empty, and error states are complete
- Keep markup and state ownership clear

### 3) Add polish selectively
- Improve spacing, hierarchy, contrast, transitions, and hover/focus feedback
- Use advanced CSS only where it improves clarity or perceived quality
- Add immersive effects only if they fit the brand, the task, and the runtime budget

### 4) Validate
- Verify responsive layouts
- Verify keyboard and screen-reader basics for edited UI
- Check Livewire interaction states and server round-trips
- Run targeted tests or framework-specific checks already used in the repo

## Design and performance guardrails
- Favor crisp typography, strong hierarchy, and restrained motion over decorative excess
- Keep interaction feedback under control; avoid cumulative latency from many micro-animations
- Watch for hydration or state-sync edge cases in Livewire flows
- Avoid visual techniques that reduce readability, contrast, or mobile performance

## Output expectations
When reporting back:
- State the requested outcome and what was actually changed
- Separate functional changes from presentation refinements
- Note any trade-offs, especially if visual polish increased complexity
- List validation performed and any limits

## Preferred deliverable shape
Use concise sections like:
- Goal
- Current constraints
- Changes made
- UX / polish notes
- Validation
- Risks / follow-ups

## Quality bar
A good result feels noticeably more refined without becoming fragile, inaccessible, or slow.
