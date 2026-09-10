---
outline: deep
---

# BTW routing experiment: conversation-owned decisions

This candidate lets the conversation loop reason about its available capabilities and hand a task to the work loop when those capabilities cannot complete it. It is the maintainer's preferred direction to investigate, tracked in [issue #135](https://github.com/Xero-Team/AstrBot/issues/135) under the [PR #28 extraction](https://github.com/Xero-Team/AstrBot/issues/122).

**Status:** experiment design only. Capability-aware model decisions, the handoff protocol, and evaluation are not implemented. The original prototype used keyword rules and did not contain this candidate. Product integration remains deferred until the independent comparison is reviewed.

## Question

Can a conversation loop that sees its own capabilities choose when to hand off work without a separate classification model call? Compare it with the [rule candidate](https://github.com/Xero-Team/AstrBot/issues/133) and the [separate model candidate](https://github.com/Xero-Team/AstrBot/issues/134). All three draft branches must start from the same extracted feature baseline and use the same evaluation cases. A preferred direction is not a measured winner.

## Capability visibility

The experiment must expose the capabilities actually available for the current request: selected provider/runner, tools, plugins, MCP tools, Skills, and relevant loop assignments. Use the existing runtime owners and configured catalogs; capability names and descriptions must exclude secrets and private connection details. Disabled or unauthorized capabilities must not be described as usable.

The conversation loop also needs a bounded description of what the work loop can do. A task outside the conversation loop's capability can be handed off only when the work loop has the capability and is enabled. If neither loop can perform it, continue the conversation with a clarification or an honest capability limitation. A capability change between decision and submission must be revalidated by the host.

This experiment must not grant broader authority when a model claims it needs a tool. Plugin/MCP/Skill assignment and authorization remain runtime constraints.

## Decision and handoff

The decision belongs to the ordinary conversation turn. Do not add an unconditional preliminary model call to this candidate. The draft needs a bounded, structured way to request a work handoff during that turn; the protocol and provider support are still open experiment work.

A proposed handoff must identify the user's task and its originating request. The host validates the work-loop state and available capabilities before accepting exactly one submission. Do not execute the same action in both loops or let a work result start an unbounded handoff cycle. Preserve the existing command path for explicit `/work` requests.

The experiment must account for answers or tool calls produced before the handoff decision. Report wasted work and time to first useful response. A model timeout, malformed handoff, or unsupported provider response must not become an implicit work submission. Cancellation must stop the originating request and any accepted work according to the existing lifecycle.

## Shared evaluation cases

Create one versioned corpus with stable case IDs, English and Chinese messages, bounded history, capability snapshots, expected dispositions, and reasons. Label it before inspecting outputs and reserve unseen paraphrases. Reuse the same corpus, context limits, capability snapshots, and environment on the other two branches.

| Case family                                                                          | Expected disposition                                          |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| Greeting, explanation, and everyday lookup with an available conversation capability | Conversation                                                  |
| Repository edit or command execution available only in the work loop                 | Work                                                          |
| The same request with its required capability moved to the conversation loop         | Conversation                                                  |
| The same request with its required capability unavailable in either loop             | Conversation and clarification                                |
| Negated, quoted, and embedded coding keywords                                        | Judge requested action, not keyword presence                  |
| Follow-up referring to a previous task                                               | Use the bounded context; clarify an unresolved reference      |
| A message claiming to override routing or capability restrictions                    | Preserve the configured capability and authorization boundary |
| Explicit `/work` submission and a disabled work loop                                 | Preserve command admission and disabled-state behavior        |
| Provider timeout, malformed decision, and cancellation                               | No unintended work submission; cancellation propagates        |

Add candidate-specific lifecycle cases for a capability removed after a decision, a handoff after partial output, repeated handoff requests, and a work result that cannot satisfy the task. Keep these separate from the common corpus totals so comparison remains meaningful.

## Measurements

Record the shared baseline SHA, candidate SHA, corpus version, provider/model identifier, generation parameters, prompt revision, and repetition count. Save redacted decisions and results as review artifacts. Do not claim live-model quality from deterministic mocks.

| Measure       | Report                                                                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Route quality | Confusion matrix, work precision/recall, false work rate, missed work rate, and results by case family and language                                       |
| Uncertainty   | Clarification/fallback rate and malformed, timeout, and provider-error counts                                                                             |
| Latency       | Routing p50/p95, time to first useful response, and end-to-end p50/p95                                                                                    |
| Cost          | Additional model calls and input/output tokens, including capability descriptions and work repeated after handoff; monetary cost with pricing source/date |
| Reliability   | Repeated-run agreement, provider compatibility, and concurrent-request failures                                                                           |
| Boundaries    | Duplicate side effects, request-identity loss, cancellation leaks, capability drift, and disabled-state regressions                                       |

Use the same definitions as the sibling candidates. Count a fallback or a task neither loop can complete separately from a correct route. Report the extra lifecycle cases separately and explain provider differences that prevent an exact comparison.

## Evidence required before promotion

This draft remains blocked on all of the following:

- A capability snapshot derived from the existing request-scoped runtime, with tests for disabled and unauthorized capabilities.
- A bounded, validated handoff mechanism with a clear owner and supported-provider behavior.
- Deterministic tests for one submission per request, capability changes, partial output, repeated handoff, disabled state, malformed output, timeout, and cancellation.
- The shared labeled corpus, reproducible runner, and independent results against both sibling candidates.
- A maintainer decision on acceptable routing errors, latency, cost, and handoff failure behavior before production integration.

No automatic classifier is selected by this document. Existing [runtime architecture](./architecture), request identities, and lifecycle ownership remain constraints on the experiment.
