<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **neuromarketer** (8101 symbols, 15329 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/neuromarketer/context` | Codebase overview, check index freshness |
| `gitnexus://repo/neuromarketer/clusters` | All functional areas |
| `gitnexus://repo/neuromarketer/processes` | All execution flows |
| `gitnexus://repo/neuromarketer/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->


<claude-mem-context>
# Memory Context

# [NeuroMarketer] recent context, 2026-04-28 1:25pm GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (15,846t read) | 351,863t work | 95% savings

### Apr 28, 2026
S126 NeuroMarketer analysis flow investigation + LLM provider upgrade recommendation — user asked about fixing notes sanitizer and checking provider config (Apr 28, 3:11 AM)
S127 Switch caveman mode to ultra level (Apr 28, 3:13 AM)
S129 Debug tribev2 ModuleNotFoundError — root cause found, fix pending user confirmation (Apr 28, 12:21 PM)
420 12:21p 🔵 NeuroMarketer tribe_runtime.py integrates tribev2 ML model
421 12:22p 🔵 tribev2 editable install broken — source path mismatch causes ModuleNotFoundError
S128 Debug tribev2 ModuleNotFoundError in NeuroMarketer backend (Apr 28, 12:22 PM)
S130 Map tribev2 import surface across NeuroMarketer backend codebase (Apr 28, 12:22 PM)
S131 Diagnose tribev2 import failure and explain relationship between HF weights and Python package (Apr 28, 12:23 PM)
422 12:25p 🔵 TribeRuntime load() uses double-checked locking singleton; requires uvx+ffmpeg+ffprobe binaries
S132 Fix tribev2 ModuleNotFoundError — completed successfully (Apr 28, 12:25 PM)
423 12:26p 🔴 tribev2 editable install fixed — reinstalled from correct source path
424 " 🔴 tribev2 import verified working — TribeModel accessible after editable reinstall
S134 Switch caveman mode to ultra intensity (Apr 28, 12:26 PM)
425 12:29p 🔵 VideoFrameStrip component — client-side frame extraction with per-frame attention/engagement/memory scores
426 " 🔵 generateFrameThumbnailMap extracts frames client-side via hidden video element + canvas seek
427 12:30p 🔵 Asset media served via 307 redirect to pre-signed URL — 30/min rate limit, 5-min cache
428 " 🔵 buildFrameBreakdownItems joins timeline+segments+heatmap with 3-tier segment fallback
429 " 🔵 VideoFrameStrip gated on stageAvailability.sceneStructureReady, not raw analysisResult
430 " 🔴 VideoFrameStrip useEffect — removed `frames` from dep array to fix thumbnail fetch abort loop
432 1:00p 🟣 New AuthRepository Class Extracted from crud.py
433 " 🔵 MFAService._get_membership Has HIGH Upstream Risk
434 " 🔵 AnalysisPageLegacy.tsx Has 7 ESLint Warnings
435 " ✅ Frontend constants.ts Quote Style Fixed to Single Quotes
436 1:01p 🔄 AuthService and Dependencies Migrated to AuthRepository
437 " 🔵 Python Runtime Uses python3 Not python
438 " 🔵 Backend Tests Require Virtualenv — starlette Not in System Python3
439 " 🔵 Refactored Backend Files Pass Syntax Check
441 " 🔵 NeuroMarketer Follows Strict Layered Architecture with Mirrored Filenames
442 " ✅ AuthRepository File Renamed auth.py → auth_repository.py to Resolve Name Collision
440 " 🔵 Full Scope of Active Refactor — crud.py Deleted, Major Frontend Analysis Split
443 1:02p ✅ Name Collision Cleanup Complete — Duplicate Count Reduced from 31 to 27
444 1:03p 🔴 session_scope Rollback Now Safe — Swallows InterfaceError/DBAPIError
445 " 🟣 InferenceRepository Gets Light Query Methods and Pipeline State Machine Integration
446 " 🟣 PredictionApplicationService Gets upsert_prediction_result and Light Status Methods
447 " 🔵 replace_analysis_result Has Active Callers in tasks.py Scoring Pipeline
449 1:06p 🔴 store_prediction_handoff Made Idempotent for Celery Retries
450 1:07p 🔴 replace_analysis_result Fully Refactored for Idempotency — Split into 3 Private Methods
448 " 🔵 PredictionApplicationService Has 5 Direct Importers — MEDIUM Risk Class
451 1:09p 🔴 replace_analysis_result AnalysisResultRecord Now Updates In-Place Instead of Delete+Reinsert
452 " ✅ upsert_prediction_result Removed from PredictionApplicationService
S133 Switch caveman mode to ultra intensity (Apr 28, 1:10 PM)
453 1:11p 🟣 Idempotency Test Suite Added for InferenceRepository Write Paths
454 " 🔴 Test File Ruff Lint Fixed — Unused Import and Import Sort
455 " 🔵 SQLAlchemy 2.0.48 Installed via pip3 But Not Importable by python3 -m unittest
456 1:12p 🔵 SQLAlchemy Installed for Python 3.14 But Tests Run on Python 3.12 — Version Mismatch
457 " 🔵 Tests Now Run on Python 3.14 — One Failure: SuggestionType.HOOK Doesn't Exist
458 " 🔴 All 5 Idempotency Tests Pass Green
459 " 🔵 13 Backend Tests Pass Green Across 5 Test Modules
460 " 🔵 Full Backend Test Suite: 86 Tests, 8 Errors — Two Failure Categories
462 " 🔵 NeuroMarketer project structure mapped
461 " 🔴 test_job_rerun Tests Broken by get_job_with_prediction → get_job_status_light Rename
463 1:13p 🔴 test_job_rerun Mocks Updated from get_job_with_prediction to get_job_status_light
464 " 🔵 NeuroMarketer DESIGN.md contains NEO MIRAI AI Design Conference token system
465 " 🔴 16 Tests Pass After Job Rerun Mock Fix
466 " ✅ test_job_rerun.py Lint Clean — 4 SIM117 Nested With Statements Collapsed
467 " 🔵 NeuroMarketer analysis feature module structure mapped
S135 Run /impeccable clarify on NeuroMarketer project (Apr 28, 1:13 PM)
468 " 🔵 Full Change Set Scope: 289 Symbols Changed Across 32 Files — Critical Risk Rating
469 " 🔵 NeuroMarketer analysis constants reveal full product domain model
470 " 🔵 AnalysisPageLegacy.tsx user-facing copy inventory completed

Access 352k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
