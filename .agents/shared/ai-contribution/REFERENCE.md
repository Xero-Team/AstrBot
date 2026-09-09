# AI contribution reference

[AI_POLICY.md](../../../AI_POLICY.md) is the authority for contributions.
Read it when committing, pushing, posting an Issue/PR, or preparing review.

Agents may commit and push feature branches and open development Issues/PRs
within the task's scope. Target `Xero-Team/AstrBot` explicitly with
`gh --repo Xero-Team/AstrBot` and verify the resulting URL. Upstream posting
needs explicit confirmation for that target.

Agents must not merge, push `master`, force-push protected branches, tag,
publish, change protection/secrets, fabricate reviews, or publicly disclose
vulnerabilities. A human maintainer merges after human and separate
AI-assisted reviews; the author agent's write-up does not count.

Use [conventional-commit/REFERENCE.md](../conventional-commit/REFERENCE.md)
for commit messages. Select the matching template in
`.github/PULL_REQUEST_TEMPLATE/`: `feat`, `fix`, `docs`, `refactor`
(also perf/style), or `chore` (also build/ops/test).
End agent-authored Issues/PRs with `## Agent note`: goal, touched paths,
actual checks, residual risks, and AI tools used. Never fabricate a Human note.
