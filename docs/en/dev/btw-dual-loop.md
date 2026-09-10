---
outline: deep
---

# BTW Dual-Loop Design

This page records the direction and capability breakdown for [PR #28](https://github.com/Xero-Team/AstrBot/pull/28). That PR delivers documentation only. The loops, commands, and settings described below are proposed follow-up work, not features available in the current release.

## Goal and Responsibilities

BTW aims to let users keep talking while a longer task runs, check its status, and receive its result. Conversation and work reuse the existing Agent execution path with different responsibilities.

| Loop         | Responsibility                                                                                                  | Intended capabilities                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Conversation | Understand requests, clarify requirements, handle requests within its abilities, and keep the interaction going | The model, tools, and Skills actually available to the current request |
| Work         | Accept explicitly submitted tasks or future handoffs from conversation, track execution, and return results     | Capabilities assigned to work, subject to existing authorization       |

The work loop is not a new permission level, and a handoff grants no additional permissions. Capability assignment determines what each loop can see. Task routing determines which loop handles a particular request. These concerns can progress separately.

## Current Decisions

- PR #28 retains this design document only. The prototype remains historical reference material; the parent Issue and Sub-issues link separate PRs for implementation and acceptance of each capability.
- Follow-up implementation starts from current master and reuses its message pipeline, Agent runners, tool catalog, and Skill snapshots. Superseded assembly and authorization logic from the prototype must not be copied back.
- The initial direction retains explicit entry and disabled defaults: `/work <task>` submits work. The prototype rule classifier is a reference candidate tested in its own experimental PR, not a predetermined production default.
- The intended later direction is: **routing belongs inside the conversation loop. The loop knows its available capabilities, handles requests it can fulfill, and hands requests that need work capabilities to the work loop.**
- Product integration of that routing direction is deferred. **Different classifiers belong in separate PRs, starting from the same baseline and tested separately under one evaluation protocol.** Results will inform the handoff contract and approach to adopt; these experiments do not block the other capability slices.

The reference prototype is commit [`33ee103a62937db3e930c89ba47a648b75cc7772`](https://github.com/Xero-Team/AstrBot/commit/33ee103a62937db3e930c89ba47a648b75cc7772). In that version, `ConversationLoop.process()` applies rules or accepts an explicit work marker before the model call. It does not implement a conversation model deciding to hand off based on its own capabilities.

## Capability Breakdown

[Parent issue #122](https://github.com/Xero-Team/AstrBot/issues/122) tracks the following capabilities and dependencies. B1–B10 each have a non-draft feature PR; R1–R3 each have a separate draft classifier PR. B/R identifiers remain design indices, with links to the actual Issues and PRs. Each slice includes its settings, Dashboard interactions, tests, and bilingual documentation instead of splitting all frontend and backend work into separate tickets. This PR neither implements nor validates the acceptance requirements in the table.

| Issue                                                         | PR                                                                | Sub-issue scope                                              | Acceptance focus                                                                                                                                                                                                                             |
| ------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [B1 / #123](https://github.com/Xero-Team/AstrBot/issues/123)  | [#136](https://github.com/Xero-Team/AstrBot/pull/136) (non-draft) | Opt-in dual-loop entry and ordinary conversation             | Disabled mode preserves the current Agent path and capabilities; enabled mode admits ordinary requests to conversation; automatic-classifier experiments are not a prerequisite.                                                             |
| [B2 / #124](https://github.com/Xero-Team/AstrBot/issues/124)  | [#139](https://github.com/Xero-Team/AstrBot/pull/139) (non-draft) | Explicit task entry with `/work <task>`                      | A registered built-in command receives the full task text; submission works with classification off; disabled work returns a clear message; command permissions and session LLM switches remain effective.                                   |
| [B3 / #125](https://github.com/Xero-Team/AstrBot/issues/125)  | [#137](https://github.com/Xero-Team/AstrBot/pull/137) (non-draft) | Background execution, concurrency, and lifecycle             | Acknowledge receipt before background execution while conversation remains available; bound concurrency; verify pending, running, completed, failed, and cancelled states; reclaim tasks at runtime shutdown.                                |
| [B4 / #126](https://github.com/Xero-Team/AstrBot/issues/126)  | [#138](https://github.com/Xero-Team/AstrBot/pull/138) (non-draft) | Result delivery and event resource release                   | Return results to the originating request through reply checks, decoration, and delivery; the acknowledgement must not prematurely end a WebChat request; release temporary files and event registrations at completion.                     |
| [B5 / #127](https://github.com/Xero-Team/AstrBot/issues/127)  | [#140](https://github.com/Xero-Team/AstrBot/pull/140) (non-draft) | Work status and retention                                    | `/work` and `/work status` report the latest task for the current profile and session; empty, terminal, and expired states are defined; profiles remain isolated and group-chat query scope is explained.                                    |
| [B6 / #128](https://github.com/Xero-Team/AstrBot/issues/128)  | [#141](https://github.com/Xero-Team/AstrBot/pull/141) (non-draft) | Model selection per loop                                     | Conversation and work may choose different models; empty selections inherit the current choice; invalid or unavailable selections have defined behavior; disabling BTW preserves ordinary model selection.                                   |
| [B7 / #129](https://github.com/Xero-Team/AstrBot/issues/129)  | [#142](https://github.com/Xero-Team/AstrBot/pull/142) (non-draft) | Computer Use boundaries per loop                             | Conversation does not mount Computer Use; work may inherit or select `none`, `local`, or `sandbox`; handoffs retain the same restrictions and loop selection does not alter permissions.                                                     |
| [B8 / #130](https://github.com/Xero-Team/AstrBot/issues/130)  | [#143](https://github.com/Xero-Team/AstrBot/pull/143) (non-draft) | Assign plugin LLM tools to loops                             | Select conversation, work, or both per plugin; the prototype defaults to work; main Agent and handoff behavior agree. Only LLM tools are affected, not plugin event handlers or the execution destination of explicit commands.              |
| [B9 / #131](https://github.com/Xero-Team/AstrBot/issues/131)  | [#144](https://github.com/Xero-Team/AstrBot/pull/144) (non-draft) | Assign MCP tools to loops by server                          | Tools from one MCP server follow a shared assignment; the prototype defaults to work; saved settings, main Agent, and handoff behavior agree while preserving MCP connection and authorization boundaries.                                   |
| [B10 / #132](https://github.com/Xero-Team/AstrBot/issues/132) | [#145](https://github.com/Xero-Team/AstrBot/pull/145) (non-draft) | Skill visibility per loop                                    | Ordinary Skills defaulted to both in the prototype; workspace Skills retain the work-loop and local-runtime boundary; prompts, `read_skill`, and declared tools use consistent filtering; reading a Skill does not require Shell permission. |
| [R1 / #133](https://github.com/Xero-Team/AstrBot/issues/133)  | [#146](https://github.com/Xero-Team/AstrBot/pull/146) (draft)     | Rule-classifier experiment PR                                | Use prototype keywords and deterministic rules as a reference; test boundaries, everyday queries, and mistakes when capabilities change; report results independently.                                                                       |
| [R2 / #134](https://github.com/Xero-Team/AstrBot/issues/134)  | [#147](https://github.com/Xero-Team/AstrBot/pull/147) (draft)     | Separate model-classifier experiment PR                      | Call a model before conversation execution to choose a destination; measure classification quality and the latency and cost of the additional call without presuming this is the final architecture.                                         |
| [R3 / #135](https://github.com/Xero-Team/AstrBot/issues/135)  | [#148](https://github.com/Xero-Team/AstrBot/pull/148) (draft)     | Capability-aware decision inside conversation, in its own PR | Let the conversation model handle or hand off requests based on available capabilities; measure unnecessary and missed handoffs and context continuity. This is the currently preferred direction to investigate.                            |

### Dependencies and Delivery Order

B1 defines the enablement boundary. B2–B5 together provide “submit → execute in the background → return results → inspect status.” An intermediate state that can acknowledge a task but cannot return its result is not a usable feature. These slices can be reviewed separately, but the first usable version needs the complete path.

B6 and B7 define each loop's model and runtime. B8–B10 deliver capability assignment separately. Shared catalog filtering or configuration controls belong to the first slice that needs them. Acceptance covers BTW enabled and disabled, and both main Agent and handoff paths.

R1–R3 are parallel alternatives with no dependency on one another; they are not a sequence of classifier implementations stacked on each other. Agree on a common baseline and evaluation protocol, then implement, test, and review each separately. Move all candidates to the same updated baseline when integration testing needs real work execution. Product integration remains a later decision after the comparison and after execution, delivery, and capability-assignment contracts are clear.

## Routing Experiment Boundaries

### Separate PRs and a Shared Evaluation Protocol

R1–R3 are initial candidates whose scope can be refined in their Sub-issues. Each completed experiment is expected to contain one classifier implementation and its tests, recording the baseline commit, dataset version, capability fixtures, model, and parameters. R2/R3 currently contain experiment plans only. Establish common cases and the evaluation harness first so implementations do not select different datasets to demonstrate success.

Run the same offline cases in each PR, followed by the same integration scenarios on a shared working dual-loop baseline. Deterministic tests check contracts; model trials separately report variation across repeated runs. Report both forms of evidence separately. Explicit `/work` entry is a control baseline for every approach, not a fourth classifier.

The parent Issue collects results, costs, and trade-offs from each PR. Do not merge all candidates together before comparison or add a production framework for switching classifiers in advance. Review integration of the selected approach separately; retain unselected implementations as experiment records.

### Capability Visibility

Conversation should see the resolved capabilities of the current request, not merely the names of every installed tool. Experiment inputs include the current model, the tool catalog after configuration and Persona filtering, the Skill snapshot, runtime restrictions, and the range of tasks that work can accept.

Use current `astrbot/core/tool_catalog.py`, main-agent catalog assembly, and Skill snapshots as the sources of truth. Avoid maintaining another capability list that can drift. Appearance in a catalog or Skill does not grant execution permission; the existing authorization service still decides at execution time.

### Questions to Resolve

- Can conversation make a different handling or handoff decision for the same request when its available capabilities change?
- Can it distinguish “needs work capabilities,” “lacks authorization,” “needs clarification,” and “neither loop can complete this,” instead of handing off every failure?
- Should handoff happen before the first action, or also after execution reveals a capability gap? If the latter is useful, how will it avoid repeating steps that already produced side effects?
- Which context, completed steps, and expected results must accompany a handoff for work to continue the same task?

These are experiment questions. This document does not prescribe a new tool interface, prompt format, or routing service.

### Cases and Measurements

Cases should cover ordinary chat, queries solvable with available tools, workspace or external execution, mixed requests, incomplete requirements, unavailable tools, insufficient permissions, and requests neither loop can fulfill. Pair the same request with different capability sets to test whether decisions actually depend on capability availability.

Measure unnecessary and missed handoffs, task completion, appropriate clarification and refusal, added latency, model calls and token cost, repeated handoffs, and duplicate execution. Start with fixed data and simulated tools rather than enabling routing in production as an experiment. State acceptance thresholds before evaluation; retaining explicit entry is a valid outcome.

## Implementation and Acceptance Constraints

- **Current path:** Reuse `AgentRequestSubStage`, the current tool catalog, and Skill snapshots. Assess external Agent runners separately: local-runner control over models and tools does not automatically apply to a remote service.
- **Authorization:** Preserve current configuration scope, role, and entry rules. BTW markers, routing decisions, and Skill declarations are not authorization credentials. This design does not restore the prototype's proposed BTW-specific elevation mechanism.
- **Request identity:** WebChat acknowledgements, `run_started`, per-model-call `agent_stats`, streamed results, completion, and interrupts stay attached to the original `message_id`. Concurrent tasks must not collapse into a session-wide busy flag.
- **Lifecycle:** Runtime owns background tasks and cancellation propagates. Verify cancellation while queued, execution and delivery failure, configuration reload, and shutdown cleanup. Terminal-state retention must not expire active tasks.
- **Configuration:** Use the current profile-save path and one configuration shape, with disabled defaults. Do not add compatibility for old prototype dictionaries. The UI must explain that ordinary Skills default to both while plugin and MCP tools default to work.
- **Verification:** Use the nearest existing backend and Dashboard tests and add regressions for each observable behavior. Background integration requires the real scheduler and WebChat protocol; a successful mock-dispatcher test does not establish end-to-end behavior.
- **Docs and interfaces:** Update command, configuration, and topic documentation in both languages as features land. Synchronize OpenAPI and generated artifacts only when the HTTP contract actually changes; this design does not require new HTTP endpoints.

## Parent Issue and Non-goals

[Parent issue #122](https://github.com/Xero-Team/AstrBot/issues/122) uses native Sub-issues to track B1–B10, dependencies, acceptance, and the R1–R3 experiment PRs and results. Feature PRs are stacked by dependency so each diff contains one capability. The three classifier drafts use the same feature baseline and are tested separately. R1 extracts the prototype's existing rules; the prototype contains no R2/R3 model classifier implementation, so those drafts initially provide experiment plans and explicit outstanding validation. Product integration of classification remains deferred.

This increment excludes persistent or resumable work, cross-device scheduling, an automatic retry or rollback platform, a multi-task management page, and enabling automatic routing by default in production. The prototype's `pyupgrade` adjustment is separate repository maintenance, outside the BTW feature scope.

Current behavior is documented in [Architecture](./architecture.md), [Computer Use](../use/computer.md), and [Skills](../use/skills.md). Implementation and acceptance are tracked in the linked Issues and PRs; this overview does not replace implementation review.
