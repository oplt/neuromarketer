# Technical Market Readiness Plan

## 1. What the app is today
- **Fact:** NeuroMarketer is a creative analysis web app with asset upload, async model inference, dashboards, comparison, and optional LLM evaluation (`README.md`, `backend/api/router/analysis.py`, `frontend/src/pages/AnalysisPage.tsx`).
- **Fact:** Stack is React 19 + TypeScript + Vite frontend and FastAPI + SQLAlchemy + Alembic + Celery backend with PostgreSQL, Redis, and MinIO/S3-compatible storage (`frontend/package.json`, `backend/requirement.txt`, `docker-compose.yml`).
- **Fact:** Core execution path is: sign in -> upload asset -> create analysis job -> dispatch async worker/in-process fallback -> stream job updates via SSE -> show result/insights/evaluations (`backend/api/router/analysis.py`, `backend/tasks.py`, `frontend/src/lib/api.ts`).
- **Fact:** Architecture follows layered backend organization (router -> application services -> repositories -> models) and a page-driven frontend with client-side session state (`backend/application/services/*`, `backend/db/repositories/*`, `backend/db/models.py`, `frontend/src/lib/session.ts`).
- **Inference:** Product maturity is **early production MVP**: strong domain scope and many operational hooks exist, but production discipline (CI/CD, enterprise controls, broad automated tests, and hardened observability) is incomplete.

## 2. Technical strengths already present
- **Solid async job orchestration with graceful fallback:** Worker probing and in-process fallback prevent total outage when broker/workers unavailable (`backend/tasks.py`).
- **Good domain-rich schema foundation:** Multi-tenant org/project model, sessions, MFA, SSO config, invites, analysis artifacts, comparison, calibration, collaboration, audit/webhook tables already modeled (`backend/db/models.py`).
- **Structured security primitives in core auth:** Password hashing, signed session tokens, MFA challenge tokens, TOTP and recovery-code paths, production secret guard (`backend/core/security.py`, `backend/core/config.py`, `backend/tests/test_security.py`).
- **Operationally useful runtime plumbing:** Correlation IDs, structured logging, `/health/live`, `/health/ready`, `/metrics`, rate limits on key endpoints, SSE event stream (`backend/api/main.py`, `backend/core/logging.py`, `backend/api/router/analysis.py`).
- **Customer-visible workflow depth already higher than many MVPs:** Upload pipeline, job rerun, partial-result preservation, creative comparison, generated variants, optional LLM evaluations (`backend/api/router/analysis.py`, `backend/tasks.py`).

## 3. Technical weaknesses and production risks
- **Fragile frontend maintainability:** `AnalysisPage.tsx` is extremely large and centralizes many concerns, increasing change risk and slowing iteration.
- **Limited automated quality gates:** Backend tests exist but are narrow and mostly unit-level; frontend has few targeted tests; no visible CI workflow files in repo.
- **Metrics implementation is basic in-process registry:** Prometheus text render exists but no histogram buckets, no durable metrics backend integration, no alerting contract (`backend/core/metrics.py`).
- **Telemetry integration is mostly stub-level:** OTel toggle and trace extraction exist but no configured exporters/pipelines by default (`backend/core/telemetry.py`).
- **Config and secret posture still risky for real production:** Compose uses `.env.example`; settings API exposes workspace env management but without explicit approval workflow/audit linkage surfaced to customers (`docker-compose.yml`, `backend/api/router/settings.py`).
- **Potential scaling bottlenecks:** Sync-style object retrieval for media endpoints, large payload handling in API process, and fallback thread executor limits under sustained load (`backend/services/storage.py`, `backend/tasks.py`).
- **Operational maturity gap:** No first-class incident runbook, no deployment pipeline codified in repo, and no explicit backup/restore automation contracts.

## 4. Market-facing technical expectations
- **Likely category:** Creative analytics / ad creative pre-flight performance intelligence with collaboration.
- **Users expect:** Fast upload + near-real-time progress, stable queues, reliable reruns, and responsive dashboards under multi-user load.
- **Buyers compare on:** Reliability SLAs, SOC2-ready controls, SSO/RBAC depth, auditability, integration breadth (ad platforms, data warehouse, webhooks/API), and export portability.
- **Trust signals expected:** Explicit uptime/error transparency, robust permission boundaries, immutable audit trails, predictable job completion, and data governance posture.
- **Missing trust signals in current product:** Public technical posture artifacts (SLA/SLO, security/compliance statement), mature observability package, and hardened enterprise admin controls.
- **External market inference (web research):** Competitive platforms increasingly emphasize cross-channel integrations, creative benchmarking at scale, collaborative reporting, governance/audit features, and predictive assistive insights.

## 5. Competitiveness gaps
| gap | why it matters | customer-visible or internal | likely competitor benchmark | business consequence if ignored |
|---|---|---|---|---|
| No visible CI/CD + release gates in-repo | Quality and deployment reliability confidence | Internal (buyer-visible during due diligence) | Automated lint/test/security checks per PR and release | Slower shipping, higher regression risk, weaker enterprise trust |
| Basic observability stack | Harder incident response and performance tuning | Internal -> customer-visible during incidents | Centralized logs, traces, dashboards, alerting, SLOs | Longer outages, unclear RCA, churn risk |
| Monolithic frontend analysis page | Slows feature velocity and increases defect rate | Internal | Modular feature slices with testable boundaries | Delivery drag and rising maintenance cost |
| Limited integration surface | Product harder to embed in real marketing stack | Customer-visible | Ad/data connectors, webhook events, robust API docs | Lost deals where stack compatibility is required |
| Audit + governance not productized end-to-end | Enterprise buyers need accountability controls | Customer-visible | Exportable audit logs, approval flows, policy controls | Procurement stalls, enterprise disqualification |
| Minimal performance/capacity controls | UX degrades as assets/users scale | Customer-visible | Queue QoS, caching, payload optimization, load-tested limits | Reliability issues in pilot expansion |
| No explicit backup/recovery posture | Data-loss fear blocks serious adoption | Customer-visible in security review | Automated backups + tested restore procedures | High-risk perception, procurement rejection |
| Limited customer-facing admin tooling | Ops burden remains on engineering | Customer-visible | Self-serve org/project/user controls and usage governance | Higher support cost, slower onboarding |

## 6. Recommended technical improvements
| recommendation | exact problem solved | customer impact (1-5) | competitive necessity (1-5) | revenue influence (1-5) | risk reduction (1-5) | effort (1-5) | fit with current stack (1-5) | recommendation priority |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Add CI pipeline (lint, unit tests, type checks, smoke API tests) | Regressions shipped without automated guardrails | 4 | 5 | 4 | 5 | 2 | 5 | P0 |
| Build production observability pack (structured metrics, tracing pipeline, alert rules, dashboards) | Incidents hard to detect/diagnose quickly | 5 | 5 | 4 | 5 | 3 | 4 | P0 |
| Split `AnalysisPage` into bounded modules + state hooks + test harness | Frontend complexity blocks speed and reliability | 4 | 4 | 4 | 4 | 3 | 5 | P1 |
| Productize audit trail + settings change history + actor attribution UI/export | Governance and trust controls not buyer-ready | 5 | 5 | 5 | 4 | 3 | 4 | P0 |
| Introduce background task reliability controls (dead-letter/retry policy, queue visibility, idempotency keys) | Async workflow unpredictability at scale | 5 | 5 | 4 | 5 | 3 | 4 | P0 |
| Expand API/webhook integration strategy with versioned contracts | Weak ecosystem fit and low extensibility | 4 | 5 | 5 | 3 | 3 | 4 | P1 |
| Add performance envelope work (response caching, media access optimization, pagination tightening, load tests) | UX and latency degrade with growth | 4 | 4 | 4 | 4 | 3 | 4 | P1 |
| Establish backup/recovery and disaster-recovery runbook with restore drills | Data resilience confidence missing | 5 | 5 | 4 | 5 | 2 | 4 | P0 |
| Harden enterprise auth controls (RBAC granularity, SSO enforcement workflows, session policy controls) | Security posture not complete for enterprise | 5 | 5 | 5 | 5 | 3 | 4 | P0 |
| Build usage metering + quota controls by org/project | No commercial/ops control surface for growth tiers | 4 | 4 | 5 | 3 | 3 | 4 | P1 |

## 7. Customer-convincing feature additions
- **Feature name:** Exportable audit timeline (filters by user/entity/time)
  - user/buyer concern it addresses: "Can we prove who changed what and when?"
  - why it helps win customers: De-risks governance and compliance reviews.
  - minimum viable implementation: API + UI table over `audit_logs`, CSV export, actor/entity filters.
  - dependency on technical foundations: Structured logging/event capture and policy around audited actions.
  - success metric: % enterprise trials passing security questionnaire first pass.

- **Feature name:** Integration hub (webhooks + API tokens + event subscriptions)
  - user/buyer concern it addresses: "Will this fit our stack?"
  - why it helps win customers: Enables workflow embedding with BI, orchestration, and marketing systems.
  - minimum viable implementation: Stable webhook delivery, retries, event signatures, API token scopes.
  - dependency on technical foundations: Auth hardening, queue reliability, versioned contracts.
  - success metric: Number of active external integrations per workspace.

- **Feature name:** Reliability center (job health, queue latency, retry status)
  - user/buyer concern it addresses: "Can we trust job outcomes and timing?"
  - why it helps win customers: Makes system reliability transparent and operationally actionable.
  - minimum viable implementation: Expose queue/job telemetry, historical durations, failure reasons, rerun actions.
  - dependency on technical foundations: Metrics/tracing and job-state instrumentation.
  - success metric: Reduction in support tickets per 100 jobs.

- **Feature name:** Benchmark library + confidence bands
  - user/buyer concern it addresses: "Are these scores good relative to market norms?"
  - why it helps win customers: Turns raw scores into decision confidence.
  - minimum viable implementation: Benchmark cohorts by media/channel/objective and percentile visualization.
  - dependency on technical foundations: Data quality controls and benchmark dataset governance.
  - success metric: Increase in decision adoption rate after analysis.

- **Feature name:** Workspace governance controls (role templates, policy presets, SSO enforcement toggles)
  - user/buyer concern it addresses: "Can we safely roll this out across teams?"
  - why it helps win customers: Reduces perceived rollout and security risk.
  - minimum viable implementation: Admin UI for role-policy templates + enforceable org-level auth controls.
  - dependency on technical foundations: Existing org/session/MFA/SSO data model and service boundaries.
  - success metric: Time-to-onboard for multi-user enterprise workspace.

## 8. Minimum credible production architecture
- **App architecture:** Keep current FastAPI + service + repository layering; formalize bounded modules and API contract tests.
- **Data layer:** PostgreSQL primary, Alembic migrations, explicit backup snapshots + restore validation; tune indexes for job and timeline-heavy reads.
- **Auth/permissions:** Preserve token/session model; enforce RBAC policy matrix across all endpoints; strengthen SSO and admin policy workflows.
- **Background processing:** Keep Celery queues with current in-process fallback, but add queue observability, idempotency, retry/dead-letter semantics, and worker autoscaling policy.
- **Caching:** Introduce targeted Redis/API response caching for high-read endpoints and media metadata; preserve cache invalidation by job status transitions.
- **Observability:** Evolve current structured logs + custom metrics to production telemetry pipeline (metrics backend, distributed tracing export, alert thresholds, SLO dashboards).
- **Security baseline:** Strong secret management, scoped API keys, signed webhook delivery, upload validation hardening, dependency vulnerability scanning, and audited admin changes.
- **Deployment approach:** Containerized API/workers with environment-specific config and immutable release tags; staged rollout with health checks and rollback.
- **Testing approach:** Mandatory CI gates: backend unit/integration tests, frontend component/flow tests, API contract tests, and async job smoke tests.
- **Failure/retry strategy:** End-to-end idempotent job submission, deterministic retry policy, stale job detection, partial-result persistence (already present), and operator-visible remediation paths.

## 9. Technical roadmap
- **Now (0-30 days)**
  - Implement CI pipeline with required checks and branch protection.
  - Ship observability v1 (dashboards for job latency/failures, alerting on queue backlog and error rates).
  - Add backup + restore runbook and first scheduled restore drill.
  - Add audited settings-change logging and minimal audit viewer.
  - why it belongs there: Highest risk-reduction and trust-impact, low-medium effort.
  - dependency notes: Uses existing logging, metrics, and settings tables.
  - expected impact: Faster incident response, fewer regressions, stronger buyer confidence.

- **Next (30-60 days)**
  - Modularize `AnalysisPage` into subdomains (upload, jobs, stream, results, collaboration).
  - Add webhook/API integration baseline with signed deliveries and retries.
  - Launch reliability center UI for queue/job health.
  - Add usage metering primitives for org/project-level limits.
  - why it belongs there: Enables scale in delivery and creates customer-visible platform maturity.
  - dependency notes: Relies on observability and auth hardening from Now phase.
  - expected impact: Better UX resilience, higher integration adoption, improved expansion readiness.

- **Later (60-120 days)**
  - Expand enterprise auth/governance controls (role templates, SSO enforcement workflows).
  - Build benchmark confidence framework and richer comparative intelligence.
  - Add advanced performance tuning/load-tested capacity targets.
  - Introduce approval workflows around high-impact config/model changes.
  - why it belongs there: Strategic differentiators after core reliability baseline is stable.
  - dependency notes: Needs clean telemetry, modular frontend, and governance event foundation.
  - expected impact: Stronger win-rate in enterprise deals and better long-term product moat.

## 10. Not worth doing yet
- Full microservices decomposition: premature complexity; current modular monolith still has headroom.
- Multi-cloud active-active architecture: high ops cost before stable single-region production fundamentals.
- Building custom feature store from scratch: low leverage before integration and reliability basics are finished.
- Aggressive real-time streaming everywhere: unnecessary for most value moments; optimize critical paths first.
- Major frontend framework rewrite: no evidence current React stack is blocking outcomes.

## 11. Final recommendation
- **Can this app become technically strong enough to compete?** Yes. Current foundation is viable and already includes valuable domain capabilities competitors require.
- **Most important technical upgrades:** CI/release gates, production observability, async reliability hardening, enterprise governance/audit controls, and backup/recovery discipline.
- **Extra features most likely to convince customers:** Exportable audit timeline, integration hub, reliability center, benchmark confidence views, and admin governance controls.
- **What should be built first, second, and third?**
  1. Reliability + trust baseline (CI, observability, backup/restore, audited settings changes).
  2. Integration + maintainability acceleration (API/webhook contracts, frontend modularization, reliability center).
  3. Enterprise and differentiation layer (governance controls, benchmark intelligence, advanced scaling/performance).

---

## Working principles

- Be concrete, not generic
- Ground repo findings in actual implementation
- Separate facts, inferences, and recommendations
- Think like a strong product engineer, not just an architect
- Prioritize technical work that changes customer outcomes
- Recommend the smallest set of upgrades that makes the product feel serious
- Avoid vanity architecture
- Prefer technical depth that supports market demand
