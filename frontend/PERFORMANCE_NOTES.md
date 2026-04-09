# Frontend Performance Notes

Focus areas validated in this pass:

- Initial font delivery:
  - moved from remote CSS import flow to local bundled `@fontsource` assets.

- Bundle shaping:
  - `frontend/vite.config.ts` now splits React, MUI core, MUI icons, and other vendor code into more stable chunks.

- Deferred UI work:
  - `frontend/src/pages/AnalysisPage.tsx`
  - `frontend/src/pages/ComparePage.tsx`
  - Goal: defer non-critical review/history sections until the main page is interactive.

- Analysis progress transport:
  - `frontend/src/pages/AnalysisPage.tsx`
  - Goal: consume lighter live progress payloads with fewer avoidable state updates while preserving polling fallback.

Recommended profiling checkpoints:

- Compare first-load waterfall before and after local font assets.
- Compare `AnalysisPage` route chunk load and time-to-interaction with and without deferred sections.
- Compare `ComparePage` first paint while saved-comparison history is deferred to idle time.
- Compare React commit count on `AnalysisPage` during an active job before and after the lighter progress-state updates.
- Compare network chatter during an active analysis run and confirm the page is not forcing full status refreshes on every stream message.

Observed targets to monitor after deployment:

- `AnalysisPage` route chunk size and lazy child fetch timing.
- `ComparePage` initial render speed on slower devices.
- Vendor chunk cache hit rate across navigation between dashboard tabs.
- `AnalysisPage` live-progress responsiveness under active jobs, especially when stream mode degrades back to polling.
