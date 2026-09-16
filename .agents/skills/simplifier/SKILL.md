---
name: simplifier
description: >
  Ship the smallest current AstrBot change that solves the task (YAGNI,
  reuse, stdlib, no new deps). Use ONLY when the user says simplifier,
  simplify, yagni, do less, shortest path, or asks to cut over-engineering,
  bloat, boilerplate, or extra dependencies. Not for planning, upstream
  sync, product audits, plugin scaffolding, or non-coding requests.
license: MIT
compatibility: >
  Codex CLI or OpenCode in the Xero-Team/AstrBot checkout. Python 3.14+;
  no extra tools.
metadata:
  author: Xero-Team
  checkout: Xero-Team/AstrBot
  based_on: DietrichGebert/ponytail (MIT)
---

# Simplifier

Write the smallest current change that works. Lazy means fewer moving parts,
not less reading. Follow `AGENTS.md`; cite it, do not paste it. Load
`REFERENCE.md` for checkout rungs and provenance.

## Locked

- Python 3.14+ only. No 3.10–3.13 fallbacks, no legacy shims, no resurrected
  deprecated APIs.
- Reuse existing helpers, stages, SDK surfaces, and lockfile-tracked
  dependencies. Do not add a package, config switch, or compatibility layer
  without a current need.
- Inline first: extract a helper only after the same logic appears three times
  or a function would grow past about 50 lines.
- Security invariants, trust-boundary validation, data-loss handling, OpenAPI
  plus generated clients, and bilingual docs are not optional when the change
  requires them.
- No unrequested comments. If a corner is cut, say so in the reply, not in
  the code.
- Agents may commit this skill when asked. They must not merge, push `master`,
  tag, or publish.

## Open

Which current path to reuse, and whether the request itself should shrink.
Ask only when a skipped piece would change user-visible behavior or
acceptance. Default to the higher ladder rung and continue.

## The ladder

Read the task and the code it touches first. Trace the real flow. Then stop
at the first rung that holds:

1. **Need it?** Speculative or "for later" → skip it and say so in one line.
2. **Already here?** Reuse the helper, pattern, or type in this checkout.
   Re-implementing a file away is slop. Reusing a deprecated path is not
   reuse; delete that path instead.
3. **Stdlib / language?** Python 3.14, pathlib, asyncio, existing Vue/CSS.
4. **Native platform?** Browser, OS, DB constraint, FastAPI/Vite feature
   already in the stack.
5. **Already installed?** Check `pyproject.toml` / `uv.lock` or the matching
   Dashboard/docs lockfile. Never add a dependency for a few lines.
6. **One line?** One line.
7. **Only then:** the minimum that works, fewest files, shortest correct diff.

Two rungs work → take the higher one. Bug fix = root cause: grep callers and
put one guard in the shared function, not a patch on the ticket's path only.

## Do not

- Add interfaces, factories, wrappers, or config for a single implementation
  or a value that never changes.
- Scaffold "for later", new test frameworks, or ad-hoc `demo()` / `__main__`
  checks. Put a focused pytest (or Dashboard vitest) next to existing
  coverage when the logic is non-trivial.
- Skip bilingual `docs/zh/` + `docs/en/` or OpenAPI regeneration to look
  smaller. Those are contracts, not bloat.
- Copy ponytail's plugin, hooks, intensity levels, or companion skills into
  `.opencode/`, `.codex/`, or this tree.
- Route plugin packages, upstream cherry-picks, product audits, or issue
  plans through this skill.

## Output

Code or a delete-list first. Then at most three short lines:
`skipped: [X], add when [Y].` Unrequested essays are complexity in prose.

Review-only requests stay a delete-list, one line each:
`<file>:<line>: <delete|stdlib|native|yagni|shrink> <what>. <replacement>.`
End with `net: -<N> lines possible.` or `Lean already. Ship.`

User insists on the larger version → build it, no re-arguing.

## Handoff

- Checkout rungs and provenance: `REFERENCE.md`
- Repo policy: `AGENTS.md`
- Plugin work: `create-astrbot-plugin`
- Upstream: `sync-upstream`
- Audits: `audit-product`
- Plans: `plan-issue`

## Verify

Run the smallest existing check that can fail the change (`uv run pytest`
on the nearest tests, focused Dashboard/docs commands when those trees
moved). Do not invent a new harness.
