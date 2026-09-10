---
outline: deep
---

# BTW routing experiment: separate model classifier

This candidate asks a separate model call to choose between the conversation loop and the work loop. It is tracked in [issue #134](https://github.com/Xero-Team/AstrBot/issues/134), as part of the [PR #28 extraction](https://github.com/Xero-Team/AstrBot/issues/122).

**Status:** experiment design only. The separate model classifier, its fixtures, and its evaluation runner are not implemented. The original prototype contained only a rule classifier. This draft does not select or enable a production routing policy.

## Question

Does a dedicated classification call improve routing enough to justify the extra model call, latency, tokens, and failure modes? Compare it with the [rule candidate](https://github.com/Xero-Team/AstrBot/issues/133) and the [conversation-owned candidate](https://github.com/Xero-Team/AstrBot/issues/135). Each candidate must use a sibling branch from the same extracted feature baseline; never evaluate one candidate on top of another.

## Decision boundary

The experiment would run inside the conversation-loop admission path before work submission. Its inputs are the current request, the same bounded conversation context used by the other candidates, and a snapshot of the capabilities available to each loop for that request. Capability descriptions must come from the configured runtime and exclude credentials and private connection details.

The model proposes `conversation` or `work`. A host-side check must validate the response and the work-loop enabled state before dispatch. A proposed route does not grant a tool, change a capability assignment, or execute the task. Missing capabilities and ambiguous intent stay in conversation for clarification. Treat malformed output, timeout, and provider failure as a failed decision and continue in conversation; do not silently start work.

Keep explicit `/work` command admission and existing authorization separate from the experiment. A disabled experiment must add no model call. Cancellation must propagate to the classification call, and any provider failure visible to a user must remain generic.

## Shared evaluation cases

Create one versioned evaluation corpus for all three branches before measuring. Each case needs a stable ID, language, message and bounded history, capability snapshot, expected disposition, and an explanation. Label the cases before viewing candidate output. Include English and Chinese paraphrases and reserve unseen paraphrases for evaluation.

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

The corpus must distinguish a wrong route from a task that neither loop can complete. A fallback to conversation is observable and must be counted rather than presented as a successful classification.

## Measurements

Record the shared baseline SHA, candidate SHA, corpus version, provider/model identifier, generation parameters, prompt revision, and number of repetitions. Keep prompts and redacted results as review artifacts. Never record API keys or private user conversations in the corpus.

| Measure       | Report                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------- |
| Route quality | Confusion matrix, work precision/recall, false work rate, missed work rate, and results by case family and language |
| Uncertainty   | Clarification/fallback rate and malformed, timeout, and provider-error counts                                       |
| Latency       | Routing p50/p95 and end-to-end p50/p95 measured separately                                                          |
| Cost          | Additional model calls and input/output tokens; monetary cost with the pricing source and date                      |
| Reliability   | Repeated-run route agreement and failures under concurrent requests                                                 |
| Boundaries    | Duplicate submissions, request-identity loss, cancellation leaks, and disabled-state regressions                    |

Use the same corpus, context limits, capability snapshots, and environment across candidates. Fix model settings and record unavoidable differences. Do not compare a single model run with an aggregate from another candidate. Local deterministic tests do not establish model routing quality.

## Evidence required before promotion

This draft remains blocked on all of the following:

- A bounded classifier implementation with validated output and no authority to execute tools.
- Deterministic tests for disabled mode, decision validation, provider failure, timeout, cancellation, and one submission per originating request.
- The shared labeled corpus and a reproducible evaluation runner.
- Independent measurements against both sibling candidates, including error cases and latency/cost.
- A maintainer decision on acceptable false work rate, missed work rate, latency, and cost, recorded before selecting a production policy.

Product integration remains deferred until the comparison is reviewed. There is no measured result or winning classifier yet. The existing [runtime architecture](./architecture) remains the source for lifecycle and pipeline ownership.
