# Simplifier checkout facts

Cite `AGENTS.md` for policy. This file maps the ladder onto this fork and
records what was kept from ponytail.

## Provenance

Adapted from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)
at the commit in `VENDOR.json` (MIT). Keep the ladder and the "never skip
safety" rule. Do not vendor the upstream plugin, hooks, commands, or skill
tree.

| Kept                                       | Dropped                                                          |
| ------------------------------------------ | ---------------------------------------------------------------- |
| Seven-rung ladder after reading the code   | `lite` / `full` / `ultra` levels                                 |
| Root-cause bug fix via shared callers      | Always-on injection and `/ponytail` commands                     |
| Skip speculative work; name when to add it | `ponytail-review`, `-audit`, `-debt`, `-gain`, `-help`           |
| No unrequested abstractions or new deps    | `ponytail:` code comments (this repo forbids unasked comments)   |
| Review delete-list as a mode of this skill | Hardware calibration notes; caveman pairing; npm/OpenCode plugin |

Karpathy-style KISS / inline-first rules already live in `AGENTS.md`. This
skill adds an explicit stop-at-first-rung pass and a skip report. It must
not restate the rest of `AGENTS.md`.

## Checkout rungs

| Rung      | Look here first                                                                                                       |
| --------- | --------------------------------------------------------------------------------------------------------------------- |
| Reuse     | Neighboring modules, `astrbot.api` for plugins, existing pipeline stages, Dashboard components                        |
| Stdlib    | Python 3.14, `pathlib.Path`, asyncio, stdlib parsing; wrap `astrbot.core.utils.astrbot_path` strings with `Path(...)` |
| Native    | Existing FastAPI envelope, Vue SFC patterns, CSS, SQLite/FAISS stores already owned by the lifecycle                  |
| Installed | `pyproject.toml` + `uv.lock`; Dashboard `pnpm-lock.yaml`; docs `pnpm-lock.yaml`; root `package-lock.json`             |

Runtime Python dependency changes must update `pyproject.toml`,
`requirements.txt`, and `uv.lock` together. Do not add a Dashboard or docs
package without its frozen lockfile.

Deprecated or compatibility paths are not reuse. Build on the current path
and remove the old one.

## Not optional

Do not treat these as over-engineering:

- Dashboard bind/auth, TLS verification, MCP private-network opt-in, DOMPurify,
  `defusedxml`, and `safe_error` / redaction
- OpenAPI source, generated client, `docs/public/openapi.json`, and matching
  tests when routes or schemas change
- Matching `docs/zh/` and `docs/en/` when user-facing behavior changes
- Import boundaries in `tests/unit/test_import_boundaries.py`
- Compensating cleanup on knowledge-base uploads
- Bounded queues, stage order, and cancellation/`CancelledError` re-raise

## Tests

Non-trivial logic gets one focused test beside the nearest existing coverage
(`tests/unit/`, `tests/agent/`, or `dashboard/tests/*.vitest.ts`). Trivial
one-liners need no new test. Do not add `demo()`, `__main__` self-checks, or
a new framework.
