# AGENTS.md

This file provides guidance to agents working in this repository.

## Project philosophy

This repository is a **modernized fork of AstrBot**. Keep it lean and
forward-looking instead of extending compatibility indefinitely.

- Do not add or preserve shims for legacy APIs, plugin formats, configuration
  shapes, or knowledge-base layouts. When touching an old/new split, build on
  the current path and remove the old one.
- Target Python 3.14+ only. Do not restore Python 3.10-3.13 fallbacks.
- Prefer the smallest current design that solves the actual problem. A change
  that only works by resurrecting a deprecated path is the wrong design.
- This fork does not publish a PyPI package. It may publish an optional GHCR
  nightly (`ghcr.io/xero-team/astrbot:nightly`) from `master`. Never present
  upstream artifacts as fork artifacts.
- `compose.yml` and `compose-with-napcat.yml` intentionally build this checkout
  with `build:` and tag it `astrbot:local`. Preserve that source-build contract;
  do not replace it with an upstream prebuilt image or with the fork nightly.
  Documentation is served from the Dashboard at `/help/`; do not restore a
  separate docs container or `docs.astrbot.app` links.
- Agents may maintain this repository. They may commit, push feature branches,
  open development Issues, and open Pull Requests. They must not merge, push
  `master`, force-push protected branches, tag, or publish releases. A human
  maintainer does those actions; do not treat a verbal exception as
  authorization. A PR lands only after a human maintainer review **and** a
  separate AI-assisted review. Follow [AI_POLICY.md](AI_POLICY.md) and
  `.agents/shared/ai-contribution/REFERENCE.md`.
- Open Issues and Pull Requests against `Xero-Team/AstrBot` only. Do not open
  them on upstream `AstrBotDevs/AstrBot`. `gh` may default to the `upstream`
  remote; pass `--repo Xero-Team/AstrBot` (or set `GH_REPO=Xero-Team/AstrBot`)
  and confirm the created URL is under `github.com/Xero-Team/AstrBot` before
  treating the action as done. Opening an Issue or PR on upstream requires
  explicit user confirmation for that target.

## Working approach

Complete the user's authorized scope. Make routine decisions from repository
evidence; ask only when a missing choice materially changes the result.
Prepare reviewable work before requesting any genuinely new authority.
Existing authorization carries through planning and skill workflows.

Keep prompts and tool context small: load only a relevant skill and the
references needed for the current step. Skills guide the task; they do not
add mandatory quizzes, approval rounds, or unrelated work. If an instruction
actually blocks progress, cite its exact source and explain the conflict.

Run checks proportional to the change and the required repository gates.
After they pass, repeat or broaden only for new changes, failures, or unresolved
risks. Report the result, evidence, and limitations concisely.

## Task references

Read the relevant section of
[the checkout reference](.agents/shared/checkout/REFERENCE.md) before working
on that surface. These retain the repository's detailed requirements.

| Task                                                          | Reference section                                                                                                                      |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Setup, toolchain, dependencies, dev servers                   | [Toolchain and setup](.agents/shared/checkout/REFERENCE.md#toolchain-and-setup)                                                        |
| Tests, formatting, quality gates                              | [Tests and checks](.agents/shared/checkout/REFERENCE.md#tests-checks-and-formatting)                                                   |
| Runtime, pipeline, providers, plugins, Dashboard, persistence | [Architecture](.agents/shared/checkout/REFERENCE.md#architecture)                                                                      |
| OpenAPI, docs, NapCat generation                              | [Generated artifacts](.agents/shared/checkout/REFERENCE.md#generated-artifacts-and-documentation)                                      |
| Upstream integration                                          | [Upstream synchronization](.agents/shared/checkout/REFERENCE.md#upstream-synchronization) and `sync-upstream`                          |
| Release preparation                                           | [Releases](.agents/shared/checkout/REFERENCE.md#releases)                                                                              |
| Commit messages or PRs                                        | [Commit reference](.agents/shared/conventional-commit/REFERENCE.md) and [AI contribution](.agents/shared/ai-contribution/REFERENCE.md) |
| Skills and development MCPs                                   | [Skill catalog](.agents/skills/README.md)                                                                                              |

## Security invariants

Treat these as design constraints, not optional hardening:

- Dashboard binding defaults to `127.0.0.1`. Binding to `0.0.0.0` or another
  non-loopback address must be an explicit deployment choice with firewall,
  authentication, and preferably TLS/reverse-proxy protection.
- `dashboard.trust_proxy_headers` defaults to false. Enable it only behind a
  trusted proxy that overwrites forwarding headers; never trust spoofable
  client headers on a directly exposed server.
- Dashboard authentication rate limiting is enabled by default and its
  per-client registry is bounded. Do not bypass the login/TOTP checks or
  reintroduce attacker-controlled, unbounded limiter state.
- Download/update HTTP clients must verify certificates and hostnames. Do not
  restore `CERT_NONE`, `ssl=False`, `verify=False`, or an automatic insecure TLS
  retry after certificate failure.
- Remote MCP URLs reject localhost/private/link-local/reserved targets by
  default and HTTP clients do not follow redirects. Private-network access is
  allowed only through the explicit per-server `allow_private_network` opt-in;
  preserve DNS/IP validation and redirect blocking.
- Sanitize all untrusted rendered HTML with DOMPurify before `v-html`. Do not
  weaken the existing README, changelog, code-rendering, or config-hint
  sanitization paths to fix display issues.
- Parse untrusted XML with `defusedxml` (as the Satori adapter does), not the
  standard library parser without equivalent protections.
- User-facing agent failures remain generic. Redact provider errors, URLs,
  credentials, tokens, and sensitive configuration before logs or API/message
  responses; use `safe_error` / `redact_sensitive_text` and preserve config API
  redaction/restoration behavior.

## Conventions

- **KISS / first principles:** do not add abstractions, dependencies, switches,
  or compatibility layers without a current need.
- **Inline first:** extract a helper when identical logic repeats at least three
  times or a continuous function would otherwise grow past roughly 50 lines.
  Do not fragment linear code into tiny wrappers.
- **Cross-platform:** consider Windows, macOS, Linux, Arm64, and x86 where the
  touched behavior applies, while retaining the Python 3.14+ baseline.
- **Paths:** use `pathlib.Path`. Runtime path helpers in
  `astrbot.core.utils.astrbot_path` return strings, so wrap them with `Path(...)`
  for path operations. Never hardcode runtime data/temp roots.
- **Runtime roots:** source checkout and runtime root differ. `ASTRBOT_ROOT` can
  relocate mutable state; most state belongs under `<root>/data/`. Tests must
  use temporary roots, never a developer's real `data/`.
- **Import boundaries:** `astrbot/api/` must not import Dashboard or concrete
  provider/platform sources. Shared core modules and built-in Stars must not
  depend on concrete sources except in the registration/discovery owners.
  `tests/unit/test_import_boundaries.py` guards key absolute-import paths;
  still review relative imports and ownership explicitly.
- **Docstrings:** use Google style (`Args:`, `Returns:`, `Raises:`). Write new
  comments in English; match surrounding Chinese only where consistency is
  materially clearer.
- **Version sync:** keep `[project].version` in `pyproject.toml` and
  `astrbot.__version__` synchronized. `astrbot/core/config/default.py` derives
  `VERSION`; do not hardcode it.
- **Fork URLs:** use `Xero-Team/AstrBot` for fork-owned repository metadata,
  clone/edit/source links, releases, and deployment claims. `AstrBotDevs`,
  `soulter`, and other upstream links are allowed only when deliberately citing
  provenance, the upstream sync source, or a service the fork still consumes;
  label that relationship instead of implying fork ownership.
- **Skills:** load from `.agents/skills/`. Policy vs facts stay split
  (`SKILL.md` vs `REFERENCE.md` / shared files). Catalog:
  `.agents/skills/README.md`. Cite those files; do not paste them.
  `archify` is a checkout-only maintainer renderer; hatch sdist excludes
  `/.agents`, and the runtime image must not copy it.
- **Commits/PRs:** use the commit and AI-contribution references linked above.
  Preserve upstream subjects on cherry-pick/adapt; see `sync-upstream`.
