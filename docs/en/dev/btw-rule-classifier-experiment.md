---
outline: deep
---

# BTW routing experiment: rule classifier

This draft extracts the original PR #28 `TaskClassifier` into an independently testable candidate. [Issue #133](https://github.com/Xero-Team/AstrBot/issues/133) tracks it under the [feature extraction](https://github.com/Xero-Team/AstrBot/issues/122). It makes no model call and does not inspect the conversation loop's capabilities.

**Status:** the keyword classifier, opt-in conversation-loop integration, and deterministic tests are present. Product selection and the shared evaluation are deferred. This candidate routes automatically only when all three settings below are enabled; manual work admission remains independent.

## Implemented behavior

`astrbot/core/agent/btw/task_classifier.py` exposes `TaskClassifier(config)` and its asynchronous `classify(event)` method. The method reads `event.message_str` and returns `TaskType.CONVERSATION` or `TaskType.WORK`. It never submits a work session or executes a tool.

All three configuration values must be enabled for a work decision:

```json
{
  "btw": {
    "enabled": true,
    "work_loop": { "enabled": true },
    "classifier": { "enabled": true }
  }
}
```

An absent classifier setting defaults to conversation. `btw.classifier.work_keywords` may provide a list or tuple of lowercase keyword strings. Missing or invalid sequence configuration uses `DEFAULT_WORK_KEYWORDS`; an empty sequence disables keyword matches. Blank and non-string entries are ignored.

Messages are trimmed and lowercased. ASCII keywords require a boundary outside letters and digits; CJK keywords use substring matching. The defaults target coding tasks and coding-agent names, and exclude broad everyday terms such as `search` and `搜索`. Explicit `/work` admission belongs to the command and conversation-loop path, not this classifier.

## Known limits

The rules use only the current message. They cannot determine which loop has a needed capability, resolve context-dependent follow-ups, or understand quoted and negated requests. For example, a question asking what `refactor` means still matches the keyword. A missed match stays in conversation, and a match is not evidence that the work loop can complete the task.

These limits must remain visible in the comparison with the [separate model candidate](https://github.com/Xero-Team/AstrBot/issues/134) and [conversation-owned candidate](https://github.com/Xero-Team/AstrBot/issues/135). Do not treat the deterministic regression suite as an accuracy benchmark or enable the rules by default because those tests pass.

## Shared evaluation cases

Evaluate all three sibling branches from the same extracted feature baseline. Prepare one versioned corpus before viewing candidate outputs. Each case needs a stable ID, English or Chinese message, bounded history, capability snapshot, expected disposition, and reason; reserve unseen paraphrases for evaluation.

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

For this candidate, unused context and capability inputs are still part of each case. Report resulting limitations; do not remove difficult cases from its denominator. Mark model-provider failure cases as not applicable to the rule decision itself while still checking work execution separately.

## Verification and promotion

Run the deterministic suite from the shared feature baseline with this candidate applied:

```bash
uv run pytest tests/unit/test_btw_task_classifier.py tests/unit/test_conversation_loop.py tests/unit/test_btw_work_loop.py tests/unit/test_btw_delivery.py tests/unit/test_config_metadata_i18n.py
```

The suite preserves the prototype's coding/everyday cases and covers token boundaries, empty input, custom/invalid keyword configuration, all enabled-state gates, command independence, and inline work completion. It also exercises distinct background requests from one origin, result delivery and cleanup, and the actual converted Dashboard control with both translations. These regressions do not establish routing accuracy on the common evaluation corpus.

Record baseline/candidate SHAs, corpus version, settings and repetitions. Report the confusion matrix, work precision/recall, false work and missed work rates by language and case family, clarification/fallback rate, routing and end-to-end p50/p95, additional model calls/tokens/cost, and duplicate or cancelled submissions. State zero additional model calls for the rule decision only; work execution can still use models.

This draft requires the common labeled corpus and evaluator, independent results against both model candidates, and a maintainer decision on acceptable routing errors, latency and cost. No comparative results are available yet. Refer to the [runtime architecture](./architecture) for the existing ownership boundaries.
