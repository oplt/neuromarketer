---
name: backend-architect
description: Design or review backend systems, APIs, data models, reliability patterns, and cloud architecture. Use when the task involves server-side architecture, service boundaries, persistence strategy, API contracts, scaling, security, or operational trade-offs.
---

# Backend Architect

Use this skill when the task is about backend system design, service decomposition, database architecture, API design, integration boundaries, security posture, scaling strategy, or production reliability.

Do not use this skill for purely frontend/UI work, small presentation-only changes, or simple code edits that do not affect architecture, persistence, interfaces, or operational behavior.

## Goals

- Produce backend designs that are robust, maintainable, observable, and secure.
- Optimize for correctness and operational simplicity before novelty.
- Make trade-offs explicit: latency, throughput, consistency, cost, and changeability.
- Preserve backward compatibility unless the task explicitly allows breaking changes.

## Working Rules

1. Start from the business and runtime requirements before choosing architecture.
2. Prefer the simplest architecture that satisfies the real constraints.
3. Treat data model and API contracts as long-lived interfaces.
4. Build in security, observability, and failure handling from the start.
5. Call out assumptions, constraints, and migration risks explicitly.
6. When proposing distributed systems, justify why a monolith or modular monolith is insufficient.
7. Prefer measurable targets over generic claims.

## Required Analysis

When applied, work through these areas:

### 1. Problem framing
- What must the backend do?
- What are the expected load, latency, consistency, compliance, and availability constraints?
- Which requirements are hard constraints vs preferences?

### 2. Architecture choice
Evaluate the most plausible options such as:
- modular monolith
- microservices
- event-driven architecture
- serverless functions
- hybrid approach

For each serious option, state:
- why it fits
- where it adds complexity
- operational cost
- main failure modes
- when it should be rejected

### 3. Data architecture
Specify:
- primary data stores and why they fit the access patterns
- schema shape and ownership boundaries
- indexing, query patterns, retention, and archival strategy
- consistency model and transaction boundaries
- migration and backward-compatibility strategy

### 4. Interface design
Define:
- API style: REST, GraphQL, gRPC, async events, or mixed
- versioning strategy
- idempotency requirements
- authn/authz model
- validation, error model, and rate limiting
- webhook or event contracts if relevant

### 5. Reliability and operations
Cover:
- retries, timeouts, circuit breakers, backpressure
- caching strategy and invalidation risks
- background jobs and queue semantics
- observability: logs, metrics, tracing, SLOs, alerts
- disaster recovery and backup posture

### 6. Security and compliance
Always check:
- least privilege
- secrets handling
- encryption in transit and at rest
- tenant isolation if multi-tenant
- auditability and data handling obligations
- abuse prevention, throttling, and input hardening

## Output Format

Structure the response like this when doing architecture work:

### Recommended approach
- concise architecture choice
- why this option is preferred
- what trade-offs are accepted

### System design
- major components and responsibilities
- data flow
- integration points
- deployment shape

### Data model and persistence
- tables/collections/streams
- ownership and boundaries
- indexes and performance considerations
- migration notes

### API and contracts
- endpoints or RPC/event surface
- versioning and compatibility
- auth and error conventions

### Reliability and security
- operational safeguards
- monitoring plan
- failure handling
- key security controls

### Risks and alternatives
- top risks
- rejected alternatives and why
- future evolution path

## When Writing Code or Schemas

If the task includes implementation:
- keep interfaces explicit and typed
- prefer incremental migrations over destructive changes
- avoid hidden coupling between services and data stores
- include validation and structured error handling
- add observability hooks where operationally important
- document assumptions in comments only where they prevent misuse

## Definition of Done

This skill has been applied well when:
- the architecture matches actual constraints rather than fashion
- data, API, reliability, and security decisions are all covered
- trade-offs are explicit and technically credible
- operational concerns are addressed, not deferred
- a teammate could implement from the output without guessing core decisions
