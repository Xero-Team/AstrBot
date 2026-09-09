# Conventional Commits

Use this reference when generating, reviewing, or classifying messages.
Upstream cherry-pick/adapt subjects follow
[sync-upstream](../../skills/sync-upstream/SKILL.md) instead of being normalized.

```text
<type>(<optional scope>): <description>

<optional explanation of motivation or tradeoff>

Fixes #123
AI-Generated: true
Generated-At: <current UTC timestamp>
```

Write an English, lowercase imperative description without a trailing period;
keep the header under about 70 characters. Use a meaningful scope, never an
issue ID. Classify by the main outcome:

| Type     | Outcome                                                    |
| -------- | ---------------------------------------------------------- |
| feat     | Add, change, or remove user-visible/API functionality      |
| fix      | Correct an existing defect                                 |
| refactor | Restructure without changing behavior                      |
| perf     | Improve performance without intended behavior change       |
| style    | Formatting or lint-only changes                            |
| test     | Test-only changes                                          |
| docs     | Documentation-only changes                                 |
| build    | Build tooling, dependencies, packaging, or versions        |
| ops      | Deployment, infrastructure, CI/CD, monitoring, or recovery |
| chore    | Maintenance with no more specific type                     |

Keep unrelated changes in separate commits. Explain non-obvious motivation or
tradeoffs in the body. Issue references belong in footers.
Breaking changes require `!` before `:` and a `BREAKING CHANGE:` footer
describing the impact.

For every AI-generated or finalized message, get a fresh timestamp:

```sh
date -u '+%Y-%m-%dT%H:%M:%SZ'
```

Append `AI-Generated: true` and `Generated-At: <result>`.
Human-authored messages may omit those footers. An unchanged upstream message
preserved by `git cherry-pick -x` does not receive AI footers.
Keep Git's standard revert format when reverting; agents do not create merges.

Release automation uses this repository's convention: breaking → major;
nonbreaking API/UI feat or fix → minor; otherwise patch. The reviewed release
policy and baseline in `AGENTS.md` take precedence.
