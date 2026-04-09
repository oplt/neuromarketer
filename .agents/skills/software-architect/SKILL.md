---
name: software-architect
description: Analyze or design software architecture when the task involves system boundaries, domain modeling, service decomposition, integration patterns, technical decision records, or trade-off analysis for scalability and maintainability.
---

# Software Architect

Use this skill for design work where the main problem is choosing the right structure, boundaries, or technical direction.

## Use this skill when
- Designing a new system or major subsystem
- Evaluating modular monolith vs microservices vs event-driven designs
- Defining bounded contexts, ownership boundaries, or integration contracts
- Producing an ADR, options analysis, migration plan, or evolution strategy
- Reviewing an existing architecture for maintainability, coupling, scaling, reliability, or observability issues

## Do not use this skill when
- The task is a small localized code change with no meaningful architectural impact
- The user only wants implementation details inside an already-set architecture
- The answer would be hand-wavy theory without concrete constraints

## Core principles
1. Start with domain and constraints, not tools.
2. Prefer reversible decisions where uncertainty is high.
3. Name trade-offs explicitly. Every gain has a cost.
4. Minimize accidental complexity.
5. Design for the team that has to operate the system, not an idealized team.
6. Separate present needs from plausible future needs; do not overbuild.
7. Document decisions and consequences, not only target diagrams.

## Analysis process
### 1) Establish context
Capture:
- Business goal
- Primary workflows
- Scale assumptions
- Data consistency needs
- Team size and ownership model
- Operational constraints
- Compliance, latency, availability, and budget requirements

### 2) Model the domain
- Identify bounded contexts and major entities
- Define ownership boundaries and critical invariants
- Note synchronous vs asynchronous interactions
- Identify where duplication is acceptable and where it is dangerous

### 3) Evaluate options
For each viable option:
- Describe the structure
- State what it optimizes for
- State what it makes harder
- Explain migration implications
- Call out failure modes and operational burden

### 4) Recommend an approach
- Make one primary recommendation
- Explain why it fits the present constraints better than alternatives
- State the conditions under which the recommendation should be revisited

### 5) Define evolution steps
- Suggest the smallest viable next architecture
- Provide a migration or sequencing plan
- Include observability, testing, and operational considerations

## Required output style
Always include:
- Problem and constraints
- At least two credible options
- Trade-offs for each option
- A recommendation with rationale
- Risks and triggers that would cause a future redesign

## ADR template
Use this when the user wants a formal decision record:

### ADR: [Decision title]
- Status:
- Context:
- Decision:
- Alternatives considered:
- Consequences:
- Follow-up actions:

## Preferred deliverable shape
Use concise sections like:
- Context
- Domain / boundaries
- Options
- Recommendation
- Migration path
- Risks

## Quality bar
A good architecture answer is specific, constraint-aware, and honest about what becomes easier and harder.
