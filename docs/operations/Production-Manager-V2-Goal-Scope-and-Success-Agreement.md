# PM V2 — Goal, Scope, and Definition of Success Agreement

**Status: Draft for approval. Approval of this agreement defines scope and success criteria. It does not by itself authorize production deployment.**

## 1. Goal

Build a **fast, dependable, continuously operating, fully modular Production Manager V2** that turns approved work into functioning, secure, compliant, documented, production-ready results without repeated prompting, lost work, interference with other work, or misleading completion claims.

PM V2 must materially improve on PM V1.

Reproducing the same recurring problems experienced in V1 would constitute **project failure**, not successful delivery of V2.

The user should not need to repeatedly say:

- proceed
- continue
- retry
- check again

If approved work exists, capacity exists, and the work can safely continue, **PM V2 must continue working.**

---

## 2. Core Operating Principle

PM V2 must operate according to this principle:

**Understand the requirements → Build it → Prove it works → Secure and validate it → Document it → Release it → Verify it in production.**

Functionality, security, compliance, reliability, documentation, and governance are all mandatory.

Security and compliance requirements should be understood before implementation so they can be built into the solution rather than discovered after development.

However, the development process must not become so burdened by governance that working functionality takes hours or days to demonstrate unnecessarily.

---

## 3. Continuous Work

PM V2 must continuously process eligible work.

When approved work exists, dependencies are available, appropriate capacity exists, and existing authority permits the work, PM V2 must automatically continue.

Completion of one task should cause the next eligible task to be selected automatically.

An open ChatGPT conversation, browser session, or repeated user prompt must **not** be required to keep work moving.

OpenClaw should be used where appropriate to maintain persistent execution and continuity.

OpenClaw is a worker or continuation mechanism, not a source of authority.

---

## 4. Blockers Must Not Stop the System

A blocked task must block **that task**, not the entire PM.

Examples include waiting for Teams approval, provider API unavailable, external service unavailable, awaiting technician assistance, or failed test requiring repair.

Unrelated eligible work must continue.

PM V2 must distinguish between retryable failures, technical defects, external dependencies, missing authority, and genuine human decisions.

Repeatedly performing the same failed action without meaningful change is not progress.

---

## 5. Automatic Recovery

PM V2 must preserve durable state and recover automatically from worker failure, process crash, service restart, computer restart, interrupted network connection, temporary provider outage, and loss of an individual worker.

Recovery must determine what already happened before retrying.

PM V2 must prevent duplicate deployments, duplicate ticket updates, duplicate notifications, duplicate provider actions, lost assignments, and forgotten work.

---

## 6. Recovery From Complete Host Failure

PM V2 must be able to recover if an entire computer becomes unavailable.

Configuration, work state, checkpoints, evidence, and required operational data must be recoverable on another authorized host.

Recovery must not replay completed actions, revive expired approvals, repeat deployments, or lose assignment history.

Host recovery must be tested.

---

## 7. Parallel Development

PM V2 must support multiple independent workstreams operating simultaneously.

Parallel development must not overwrite another workstream, silently remove another change, corrupt a shared worktree, interfere with healthy production, or cause unrelated changes to be included accidentally.

Independent work should use isolated development environments or workspaces.

Integration must deliberately preserve every intended change and test the combined result.

---

## 8. Single Source of Truth for Work State

Each assignment must have one durable canonical work record.

That record should identify objective, owner or worker, current state, scope, applicable standards, completed work, remaining work, blockers, dependencies, evidence, approvals, retries, failures, test results, release state, and completion percentage.

Chat, Teams, GitHub, logs, and dashboards may display work state, but they must not independently invent competing versions of truth.

---

## 9. Idempotency

All retryable or externally meaningful operations must be designed to safely tolerate retries.

Before repeating an action, PM V2 must determine whether the intended result already occurred.

This is especially important for deployments, Autotask changes, Datto actions, Teams approvals, Teams notifications, provider writes, configuration changes, and work dispatch.

A recovery event must not turn into duplicate execution.

---

## 10. Modular Architecture

PM V2 must be **fully modular**.

It does not need to live entirely on the second computer.

Each major component must have one primary responsibility, a defined interface, explicit inputs and outputs, defined dependencies, health reporting, configuration, versioning, and independent deployment capability.

Components should be movable among authorized infrastructure without rewriting their business logic.

The architecture should support the Jason host, second computer, additional local computers, virtual machines, containers, future AWS deployment, and other authorized infrastructure.

Infrastructure placement should be a configuration and deployment concern, not a redesign.

---

## 11. Distributed Load

PM V2 should be capable of distributing work across multiple available resources.

Examples include engineering workers, testing workers, validation workers, documentation processing, CI tasks, provider acceptance, and monitoring.

One unavailable worker or computer must not unnecessarily stop the entire system.

Resource placement should support future horizontal scaling.

---

## 12. Reuse Before Rebuilding

PM V2 and everything PM V2 builds must follow a **reuse-first principle**.

Before creating a new capability, determine whether a verified shared capability already exists.

Examples include Teams approval, Teams notification delivery, communication formatting, audit recording, identity verification, provider access, deployment controls, rollback handling, and evidence collection.

Do not build multiple slightly different versions of the same process.

The preferred order is:

**Reuse existing capability → Configure legitimate differences → Extend a shared component → Build something new only when necessary.**

If a new reusable resource is needed, build it once and make it available to future workflows.

Duplicating a shared capability requires a documented technical reason.

---

## 13. Configuration Before Code

Where practical, behavior should be controlled through validated configuration rather than requiring code changes.

Configuration should be used for appropriate items such as worker placement, concurrency, retry policy, timeout values, schedules, feature enablement, provider mappings, approval requirements, Teams recipients, notification formats, validation rules, resource limits, environment settings, and communication settings.

Configuration must be validated, version controlled, auditable, portable, and recoverable.

Configuration must never silently create new authority or bypass approval requirements.

If a safe operational difference can be expressed through configuration, changing it should not require rebuilding the system.

---

## 14. Requirements Before Development

Before substantial implementation begins, an assignment should establish the functional objective, expected outcome, authorized scope, applicable security requirements, applicable compliance requirements, documentation expectations, communication requirements, and acceptance criteria.

Development should continuously work against those requirements.

Independent validation should confirm compliance, not become the first place obvious requirements are discovered.

---

## 15. Functional Proof Is Mandatory

Passing automated tests does not prove a feature works.

A successful merge does not prove a feature works.

A successful deployment does not prove a feature works.

Where practical and authorized, PM V2 must test the actual requested functionality through its intended operational path.

A capability is not complete until the intended behavior has been verified.

Production success may only be declared after appropriate post-deployment verification.

---

## 16. Security and Compliance

PM V2 must preserve the existing Jason principles of human governance, least privilege, deterministic authority checks, explicit approvals where required, auditability, traceable evidence, fail-safe behavior, and non-disruptive defaults.

Security and compliance should be built into the implementation from the beginning.

They should not become unnecessary development bottlenecks where functional development can safely continue independently.

Security or compliance concerns discovered during development must be reported and corrected.

They must not be silently ignored.

---

## 17. Documentation

Documentation is a completion requirement.

Relevant work must document what changed, why it changed, intended behavior, configuration, dependencies, approvals, test evidence, operational requirements, known limitations, rollback or recovery method, and significant architectural decisions.

Documentation should be generated or maintained as part of the workflow rather than reconstructed after the project is complete.

---

## 18. Communication Standard

PM V2 must follow the established AOT communication standard consistently.

Applicable status communication should contain:

**Status**  
**Completed**  
**Still required**  
**What I’m doing next**  
**What you need to do**

Completion percentages must reflect verified deliverables and acceptance criteria.

They must not represent effort spent, number of attempts, number of files changed, or optimistic estimates.

Verified facts, assumptions, and unknowns must be clearly distinguished.

PM V2 must not report something as completed unless it has appropriate evidence.

---

## 19. Teams Is the Approval Process

**Teams is the approval interface.**

The user must not be required to SSH into Jason, enter a terminal command, edit an approval file, change a database value, set a flag, or run a script in order to provide normal approval.

Every action requiring user approval must be approvable from the existing authenticated Teams approval process.

Approval must bind to the exact action and scope presented.

Production approval must bind to the exact release identity.

If the candidate changes materially, a new approval is required.

---

## 20. Required Teams Production Messages

Every production release must use the shared Teams approval and communication resources.

Three stages are mandatory.

### Approval Request

Before deployment, Teams must present what will change, intended outcome, expected impact, exact release identity, exact SHA where applicable, relevant acceptance evidence, rollback identity, meaningful risks, and Approve / Reject controls.

### Production Push Started

When deployment actually begins, Teams must send a message identifying the release, scope, start state, and relevant progress information.

### Production Push Result

After post-deployment verification, Teams must report verified successful, failed, rolled back, or unresolved verification as appropriate.

The message must include relevant evidence, completion status, and any required action.

A deployment must never be called successful merely because files or containers were updated.

---

## 21. Terminal Assistance for Real Problems

The user is willing to use the Jason terminal when it is genuinely helpful to resolve a technical problem.

PM V2 should not silently stop because it cannot independently resolve an issue.

If reasonable automated recovery has failed and user assistance can move the work forward, PM V2 should promptly provide the exact command, exact location where it should run, what it does, why it is needed, meaningful risk, and expected result.

After the user performs the repair, PM V2 should verify the result and continue automatically.

A terminal repair is **not** an approval mechanism.

Authorization still occurs through Teams where required.

---

## 22. To-Do List

PM V2 must be capable of reading the approved Jason to-do list.

When capacity exists, it should identify eligible approved work based on priority, dependencies, authority, current ownership, and available resources.

It should pick up eligible work automatically.

PM V1 and PM V2 must coordinate ownership so they do not independently perform the same work.

---

## 23. Ideas List

PM V2 should also review the Jason ideas list.

Ideas may be researched, analyzed, grouped, refined, and proposed for implementation.

An idea does **not** constitute authorization.

Useful ideas should flow into the established approval process before becoming implementation assignments.

---

## 24. Self-Improvement

PM V2 should learn from its own operational failures.

Recurring failures, excessive delays, repeated manual intervention, and communication failures should generate evidence-backed improvement proposals.

PM V2 may improve itself only under normal governance.

It may not approve its own authority, weaken approval requirements, bypass security, expand its permissions, or silently modify governance.

Self-improvements should demonstrate measurable benefit.

---

## 25. V1 Failure Corpus

Known recurring V1 failures must become permanent V2 regression scenarios.

Examples include work stopping unnecessarily, repeated requests to “continue,” repeated unchanged retries, provider blockers stopping unrelated work, communication-standard violations, inaccurate completion claims, passing tests without working functionality, lost continuity, approval friction, unnecessary manual approval commands, integration interference, duplicate work, unnecessary process overhead, and unnecessary rebuilding of reusable functionality.

For each important failure:

**Evidence → Root cause → V2 correction → Acceptance test**

PM V2 must prove that it addresses real failures rather than assumptions about those failures.

---

## 26. Health and Self-Test

Every significant PM V2 component must expose a health or self-test mechanism sufficient to determine whether the component is alive, configuration is valid, required dependencies are reachable, required storage is available, and its primary function is operational.

Health information should allow PM V2 to route around failed resources where possible instead of simply stopping.

A process merely running does not necessarily mean it is healthy.

---

## 27. Resource and Cost Controls

PM V2 must have configurable operational limits for worker concurrency, CPU, memory, provider request volume, AI consumption, cloud usage, and other significant resources.

PM V2 must not overwhelm healthy production services.

Increased spending authority or significant new cloud consumption requires appropriate Teams approval.

---

## 28. Scope Control

Every assignment must have an agreed outcome.

Necessary corrections that are part of delivering that outcome remain part of the assignment.

Unrelated discoveries or feature ideas should become separate proposals rather than silently expanding scope.

Security or compliance issues that materially affect the assignment must be surfaced.

---

## 29. V1 and V2 Coexistence

PM V1 remains operational while PM V2 is built and evaluated.

PM V2 should initially operate in isolated development and preproduction roles.

PM V1 and PM V2 must not independently deploy competing releases to the same production target.

Healthy production must remain protected from development failures.

Replacing V1 requires sustained evidence that V2 is better, demonstrated reliability, successful representative workloads, tested fallback, and separate Teams approval.

A single successful demonstration does not justify replacing V1.

---

## 30. Bootstrap Strategy

The initial PM V2 build should prioritize creating the mechanism that allows PM V2 to continue developing without requiring repeated user prompts.

The first useful bootstrap should include a persistent work queue, durable assignment state, checkpointing, worker dispatch, automatic next-work selection, restart recovery, basic health reporting, Teams integration, and OpenClaw continuation where appropriate.

Once this bootstrap is operational and approved, PM V2 should be capable of progressing on additional approved V2 components without requiring the user to continually say “proceed.”

---

## 31. Definition of Success

PM V2 must demonstrate the following before being considered successful.

### Continuous Work
Eligible queued work progresses without repeated prompts.

### Parallel Work
Independent workstreams complete without overwriting, losing, or unintentionally combining work.

### Recovery
Worker failures, process restarts, network interruptions, and host loss do not cause lost assignments or duplicate actions.

### Blocker Isolation
One blocked assignment does not stop unrelated eligible work.

### Functional Acceptance
Representative features perform their actual intended jobs.

### Security and Compliance
Applicable requirements are satisfied and supported by evidence.

### Documentation
The resulting system and work are sufficiently documented to operate and recover.

### Teams Approval
A production release can be approved entirely through Teams.

### Production Communication
Approval, start, and verified-result cards function correctly.

### Portability
Components can be moved between authorized infrastructure without rewriting their business logic.

### Reuse
Multiple workflows successfully use shared resources such as Teams approvals and notifications.

### Configuration
Legitimate operational differences can be changed through configuration where appropriate rather than rebuilding the system.

### Reliability
The system recovers from faults rather than simply abandoning work.

---

## 32. Proposed Pilot Acceptance Targets

These values are proposed initial targets and may be adjusted by agreement before implementation.

### Dispatch
Eligible queued work should normally begin within **60 seconds** when required capacity and dependencies are available.

### Recovery
Interrupted eligible work should normally resume or be safely reassigned within **5 minutes** after required infrastructure becomes available.

### Continuous Operation
Complete a **24-hour controlled run** containing multiple queued assignments, parallel work, injected worker failure, interrupted connectivity, blocked approval, and unavailable dependency.

The run should require **zero routine “continue” prompts** and produce zero lost assignments, zero duplicate external actions, and zero unauthorized actions.

### Speed Improvement
For agreed comparable workloads, target at least a **50% reduction in request-to-production-ready elapsed time compared with PM V1**, excluding human approval waiting time.

Timing must be measured rather than guessed.

Speed cannot justify bypassing security, compliance, correctness, or approval requirements.

---

## 33. Representative Acceptance Work

The acceptance program should include real representative work rather than only synthetic demonstrations.

A **VulScan playbook/runbook change** should be included because it represents several of the problems PM V2 is specifically intended to solve.

Other representative workloads should be selected to exercise parallel development, reusable Teams approval, configuration changes, provider-backed functionality, documentation, recovery, integration, and production verification.

---

## 34. What Does Not Count as Success

PM V2 is not successful merely because services are running, tests pass, a PR merges, deployment completes, or a worker says the task is finished.

PM V2 is not accepted if it regularly requires repeated prompting, silently abandons work, retries unchanged failures indefinitely, ignores established communication standards, loses work, interferes with unrelated development, disrupts healthy production, reports unverified functionality as complete, requires terminal commands for normal approvals, unnecessarily rebuilds capabilities already available, or becomes difficult to move or maintain.

Failures may occur.

**Failing to recover, failing to communicate accurately, or requiring the user to repeatedly rescue the workflow is what PM V2 is specifically being designed to eliminate.**

---

## 35. Approval Boundary

Approval of this agreement means:

**We agree that this document defines the goal, scope, design principles, and success criteria for PM V2.**

It does not automatically authorize production deployment, replacement of PM V1, new cloud spending, unrestricted new permissions, or bypassing existing governance.

After agreement, the next step is to define the PM V2 component architecture and bootstrap plan.

Actual implementation begins only after explicit authorization to begin the PM V2 build.

---

## Agreement Statement

**PM V2 will be designed and built as a fast, modular, reusable, configuration-driven, continuously operating production-management system that reliably completes approved work, survives failures, works safely in parallel, uses Teams as its approval interface, follows AOT communication standards, and proves actual functionality before claiming completion.**

**The project is successful only if PM V2 demonstrably eliminates or substantially improves the recurring operational failures experienced with PM V1 while preserving security, compliance, documentation, governance, and production safety.**