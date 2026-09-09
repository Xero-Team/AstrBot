# Skills

`.agents/skills/` is the only skill source in this repository. Each skill is a
directory with `SKILL.md` (shared instructions) plus optional `REFERENCE.md`,
`scripts/`, and `agents/openai.yaml` (Codex UI metadata).

## Codex CLI and OpenCode

Both clients discover `.agents/skills/<name>/SKILL.md`. Keep one source tree;
do not copy skills into `.codex/` or `.opencode/`. Repository rules remain in
`AGENTS.md`, which both clients support.

In Codex, invoke a skill with a `$skill-name` mention, for example:

```text
Use $plan-issue to turn issue 123 into a plan with exact files and checks.
```

In OpenCode, ask for the same skill by name; its `skill` tool loads the shared
instructions. For example:

```text
Use the plan-issue skill to turn issue 123 into a plan with exact files and checks.
```

`agents/openai.yaml` supplies short labels and starter prompts for Codex. It
must not contain workflow requirements missing from `SKILL.md`; OpenCode does
not need that metadata to execute the skill. Use the active client's available
shell, question, browser, and delegation tools. If a tool is missing, use an
equivalent capability or report the specific unverified part.

Discovery references: [Codex skills](https://learn.chatgpt.com/docs/build-skills)
and [OpenCode skills](https://opencode.ai/docs/skills/).

Shared locks live under `.agents/shared/`:

| Path                               | Role                                             |
| ---------------------------------- | ------------------------------------------------ |
| `conventional-commit/REFERENCE.md` | Commit message shape                             |
| `ai-contribution/REFERENCE.md`     | What agents may open vs what they must not merge |

## Catalog

| Skill                   | Load when                                                             |
| ----------------------- | --------------------------------------------------------------------- |
| `sync-upstream`         | Absorb `AstrBotDevs/AstrBot` `master`                                 |
| `create-astrbot-plugin` | Create or repair a plugin (Star) package                              |
| `archify`               | Checkout-only diagram renderer; not shipped in sdist, wheel, or image |
| `audit-product`         | Baseline or module product audit; Chinese Markdown report + diagrams  |
| `plan-issue`            | Issue or pasted request → research, clarify, file-path plan           |

Do not add a skill that only restates `AGENTS.md`. Split a skill when a
second, independently loadable workflow appears.

## `SKILL.md` contract

Frontmatter uses a stable directory-matching `name` and a concise `description`
that leads with the capability and trigger. Add exclusions only to prevent
likely misrouting. Keep workflow detail in the body and load supporting
references when needed. The body may use these headings where helpful:

- **Locked** — toolchain or behavior the agent must not change
- **Open** — product design the agent may decide
- **Do not** — hard stops
- **Handoff** — other skills or files to cite, not paste
- **Verify** — focused commands after the change

Cite `AGENTS.md` and shared references. Do not inline those files.

Plugin sibling repositories should call this checkout's
`create-astrbot-plugin/scripts/check_plugin.py` rather than vendoring a copy of
the skill.

`archify` is a vendored MIT renderer from
[tt-a1i/archify](https://github.com/tt-a1i/archify). It is a checkout-only
maintainer tool: hatch sdist excludes `/.agents`, and `.dockerignore` drops
`.agents/` from the image build context. Keep the overlay in
`archify/REFERENCE.md` and the pin in `archify/VENDOR.json`. Agents load it
from `.agents/skills/archify/SKILL.md`. Verify with `make check-archify`; that
target is not part of `make check`.

`audit-product` writes working state under `.tmp/product-audit/` (gitignored)
and diagrams via `archify`. Reports stay out of `docs/` unless the user
explicitly asks to promote a figure. Security findings follow `SECURITY.md`.
Official-standard URLs live in `audit-product/references/standards.md`; cite
them, do not paste the specs. Independent disprove, variant sweeps, and GHA
bars live in `audit-product/references/verification.md`. Do not vendor
third-party audit skill trees into `.agents/skills/`.

`plan-issue` writes working state under `.tmp/issue-plan/` (gitignored). Direct
planning is the default; use `init --skip-probe` and record the reason without
inventing a user waiver. A guided interview is optional when requested. A
planning-only request ends at validated `PLAN.md`; implementation authorization
already given in the conversation remains valid. Cite
`plan-issue/references/sources.md` for Superpowers, triage,
Spec Kit, grilling, JTBD, and related planning skills; do not vendor
those trees or their default `docs/superpowers/`, `tasks/`, `.specify/`,
or `dev/plans/` directories. The plan checker in
`plan-issue/references/verification.md` is the agent judgment pass;
`scripts/issue_plan.py validate` owns mechanical bars.
