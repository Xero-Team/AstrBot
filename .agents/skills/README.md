# Skills

`.agents/skills/` is the only skill source in this repository. Each skill is a
directory with `SKILL.md` (policy) plus optional `REFERENCE.md`, `scripts/`,
and `agents/openai.yaml`.

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

Frontmatter `name` and `description` must say **when to load** and **when not
to**. The body uses these headings when they apply:

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

`plan-issue` writes working state under `.tmp/issue-plan/` (gitignored). It
stops at `PLAN.md` until the user approves implementation. Brief, quiz,
reflect, and grill are required unless the user explicitly skips that
Q&A. Cite `plan-issue/references/sources.md` for Superpowers, triage,
Spec Kit, grilling, JTBD, and related planning skills; do not vendor
those trees or their default `docs/superpowers/`, `tasks/`, `.specify/`,
or `dev/plans/` directories. The plan checker in
`plan-issue/references/verification.md` is the agent judgment pass;
`scripts/issue_plan.py validate` owns mechanical bars.
