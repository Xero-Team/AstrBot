# AGENTS.md

This file provides guidance to Agents when working with code in this repository.

## Project philosophy

This repository is a **modernized fork of AstrBot**. The guiding principle is to keep the codebase lean and forward-looking rather than infinitely backward-compatible.

- **Do not add or preserve compatibility shims for legacy APIs, old plugin formats, or deprecated knowledge-base layouts.** When you touch code that carries such compatibility layers, prefer removing the legacy path over extending it.
- Target the current Python and platform baseline only (Python 3.14+). Do not reintroduce 3.10/3.11/3.12/3.13 fallbacks.
- When a feature has an old and a new code path, build on the new one and delete the old one rather than bridging the two.

If a change would require resurrecting a legacy compatibility layer to work, that is a signal the approach is wrong — find the modern path instead.

## Setup & common commands

### Backend (Python, managed by `uv`)

```bash
uv sync --group dev     # install runtime plus test/quality dependencies
uv run main.py          # run AstrBot; WebUI/API on http://localhost:6185
```

On first startup, AstrBot generates a random WebUI password, prints it in startup logs, and uses the default username `astrbot` until you change it. Runtime data (config, plugins, temp) lives under `data/`.

### Dashboard (Vue 3 + Vite, managed by `pnpm`)

```bash
corepack enable
cd dashboard
corepack pnpm install       # first time only
corepack pnpm dev           # http://localhost:3000
corepack pnpm build         # type-check and build into dashboard/dist/
corepack pnpm test          # Vitest suite
corepack pnpm generate:api  # regenerate the typed API client (see below)
```

The dashboard's pinned pnpm version is declared in `dashboard/package.json`; use Corepack rather than a globally installed pnpm. `make build`, `make run`, `make stop`, and `make status` provide the integrated backend/dashboard workflow (GNU Make and PowerShell 7 are required). `make run` performs a build first, so use the direct backend or dashboard commands during focused iteration.

### Tests

```bash
uv run pytest                                  # full suite
uv run pytest tests/unit                       # unit tests only
uv run pytest tests/unit/test_event_bus.py     # single file
uv run pytest tests/unit/test_event_bus.py::TestEventBusDispatch::test_dispatch_processes_event  # single test
uv run pytest --test-profile blocking          # exclude auto-classified tier_c/tier_d (slow/integration) tests
```

Tests use `pytest-asyncio`; async tests are marked explicitly with `@pytest.mark.asyncio`. `tests/conftest.py` sets `TESTING=true` and `ASTRBOT_TEST_MODE=true`, reorders unit tests before integration tests, and auto-classifies slow/platform/provider tests as `tier_c` and integration tests as `tier_d`. Provider/platform-marked tests may require their documented environment variables and otherwise skip. Shared fixtures (`event_queue`, `temp_data_dir`, etc.) live in `tests/conftest.py` and `tests/fixtures/`.

Backend tests are split between focused tests under `tests/unit/`, broad feature tests under `tests/test_*.py`, and specialist directories such as `tests/agent/` and `tests/test_kook/`. Put regression tests next to the nearest existing coverage rather than assuming every unit test belongs in `tests/unit/`. Dashboard tests use Vitest and live under `dashboard/tests/` as `*.vitest.ts`.

### Lint, format, quality

```bash
uv run ruff format .    # format Python (run before committing)
uv run ruff check .     # lint Python
make check-py           # Python format check + lint
make check-web          # dashboard build + ESLint + Vitest smoke + Prettier
make check              # repository-wide, CI-equivalent checks without writes
make quality            # focused pyright + security + audit + complexity gates
make quality-report     # broader non-gating report across astrbot
```

`make format` writes across Python, dashboard, structured data, Markdown, TOML, YAML, shell, PowerShell, and line endings; use the scoped `format-*` target when unrelated files should stay untouched. Some repository-wide checks require Node/Corepack, PowerShell 7, and native shell/Docker linters; missing optional native linters are reported locally but enforced in CI.

`ruff` is configured in `pyproject.toml` (line-length 88, py314 target, mccabe max-complexity 15). Pre-commit hooks run `ruff-check`, `ruff-format`, and `pyupgrade --py314-plus`:

```bash
pip install pre-commit && pre-commit install
```

## Architecture

AstrBot routes incoming messages from many IM platforms through a staged pipeline that ultimately invokes an LLM agent and/or plugins, then sends a response back. The big pieces:

### Startup and ownership

- `main.py` applies startup-only environment flags before importing core modules, validates Python/runtime paths, resolves a version-matched dashboard build, creates `RuntimeServices`, and hands control to `InitialLoader` (`astrbot/core/initial_loader.py`). Keep imports above `runtime_bootstrap.initialize_runtime_bootstrap()` minimal because bootstrap must run first.
- `RuntimeServices` (`astrbot/core/runtime_services.py`) explicitly owns configuration, database, shared preferences, HTML renderer, file-token service, pip installer, and demo-mode state. Pass these capabilities through existing owners instead of recreating process-global singletons.
- `InitialLoader` initializes `AstrBotCoreLifecycle` and runs it alongside `AstrBotDashboard`. `AstrBotCoreLifecycle` owns manager startup/shutdown, bounded event queues, pipeline schedulers, plugin lifecycle, cron, memory/persona runtime, knowledge base, and background task cleanup.

### Message flow

1. **Platform adapters** (`astrbot/core/platform/sources/*`) connect to each IM (QQ official, OneBot/aiocqhttp, Telegram, Discord, Lark, DingTalk, Slack, etc.). Each adapter normalizes inbound messages into an `AstrMessageEvent` (`astrbot/core/platform/astr_message_event.py`) and pushes it onto a shared asyncio queue.
2. **`EventBus`** (`astrbot/core/event_bus.py`) pulls events off the bounded queue, looks up the right `PipelineScheduler` for the event's config (keyed by config id via `AstrBotConfigManager`), and runs it under a concurrency semaphore while retaining task references for clean shutdown.
3. **Pipeline** (`astrbot/core/pipeline/`) runs the event through ordered stages defined in `stage_order.py`:
   `WakingCheck → WhitelistCheck → SessionStatusCheck → RateLimit → ContentSafetyCheck → PreProcess → Process → ResultDecorate → Respond`.
   The scheduler supports ordinary async stages and async-generator stages used as onion-style pre/post middleware. The **ProcessStage** is where plugins (Stars) and the LLM agent run; `ResultDecorate` applies reply prefixes, text-to-image, TTS; `Respond` sends the message back through the platform adapter. Preserve stage ordering and stop-propagation semantics when editing the pipeline.

### Agent & providers

- **`astrbot/core/agent/`** is the LLM agent runtime: tool execution (`tool_executor.py`), MCP client (`mcp_client.py`), handoffs, runners, and run context. The main agent assembly lives in `astrbot/core/astr_main_agent.py` and related `astr_agent_*` modules. `astrbot/core/subagent_orchestrator.py` manages sub-agents.
- **`astrbot/core/provider/`** abstracts LLM/STT/TTS/embedding/rerank services. Concrete integrations live in `provider/sources/*` (OpenAI, Anthropic, Gemini, Dify, etc.). `ProviderManager` (`provider/manager.py`) tracks instances and the default provider; `func_tool_manager.py` manages function tools exposed to the LLM.

### Plugins ("Stars")

- The plugin system is under `astrbot/core/star/`. Plugins are called **Stars**; `StarMetadata` (`star/star.py`) describes each one. Built-in plugins live in `astrbot/builtin_stars/`; user-installed plugins load from `data/plugins/`. `PluginManager` (`star_manager.py`) loads/registers them and `star_handler.py` wires their handlers and filters into the pipeline. Plugin-facing code should import the supported SDK from `astrbot.api`, as the built-in Stars do, rather than reaching into provider/platform source implementations.

### Lifecycle & supporting subsystems

- **`AstrBotCoreLifecycle`** (`astrbot/core/core_lifecycle.py`) is the startup/shutdown orchestrator. It constructs the provider/platform/conversation/plugin managers, pipeline schedulers, event bus, cron manager, knowledge base, memory manager, persona managers, and sub-agent orchestrator, then owns their tasks and termination order.
- Other core subsystems: `knowledge_base/` (chunking + retrieval, FAISS/BM25), `conversation_mgr.py`, `memory/`, `persona_mgr.py`, `persona_runtime/`, `cron/` (APScheduler-based jobs), `skills/`, `computer/` (agent sandbox), `db/`, and `backup/`.

### Dashboard ↔ backend contract

- The backend is a FastAPI application under `astrbot/dashboard/`. Route modules live in `astrbot/dashboard/api/`, are mounted under `/api/v1` by `api/router.py`, and should delegate domain work to `astrbot/dashboard/services/`. Request models belong in `astrbot/dashboard/schemas.py`; successful/error responses use the envelope helpers in `astrbot/dashboard/responses.py`.
- The source-of-truth OpenAPI definition is `openspec/openapi-v1.yaml`. The frontend typed client under `dashboard/src/api/generated/openapi-v1/` is generated by Hey API and wrapped/configured by `dashboard/src/api/v1.ts`. **When you change backend routes, request/response schemas, or the OpenAPI spec, run both commands below and commit the generated client/docs output:**

  ```bash
  cd dashboard && corepack pnpm generate:api
  uv run python docs/scripts/update_openapi_json.py
  ```

  Do not hand-edit generated client files. Keep runtime routes, the source spec, frontend call sites, and relevant backend/frontend tests in the same change.

### CLI

The `astrbot` console entry point (`astrbot/cli/__main__.py`, commands in `astrbot/cli/commands/`) drives `astrbot init` / `astrbot run` for `uv tool` installs.

## Conventions

- **KISS / first principles.** Identify the real problem and the smallest correct change. Do not add features, config switches, abstractions, dependencies, or compatibility layers without clear, current need.
- **Inline-first, few helpers.** Implement logic inline within the main function. Only extract a helper when the exact logic repeats in 3+ places or inlining makes a function exceed ~50 lines. Do not split continuous linear logic into tiny functions. When editing existing code, don't restructure or extract helpers unless the code already violates these rules.
- **Cross-platform.** When relevant, consider behavior on Windows, macOS, and Linux, and on Arm64/x86 platforms, while keeping the current Python 3.14+ baseline.
- **Paths:** use `pathlib.Path`, not string paths. Get AstrBot data/temp directories via `astrbot.core.utils.astrbot_path` (e.g. `get_astrbot_data_path()`, `get_astrbot_temp_path()`) — don't hardcode.
- **Runtime roots:** source checkout location and runtime root are distinct. `ASTRBOT_ROOT` may relocate runtime state; most mutable state belongs under `<root>/data/`. Do not import from or write tests against a developer's real `data/` directory.
- **Import boundaries:** public plugin surfaces under `astrbot/api/` must not import `astrbot.dashboard` or concrete provider/platform sources. Shared core modules must not depend on concrete `platform/sources` or `provider/sources`; registration/discovery owns those imports. `tests/unit/test_import_boundaries.py` enforces this.
- **Async lifecycle:** any task, client, file, temporary asset, database/session resource, or subprocess created by a long-lived component needs an explicit shutdown/cleanup path. Preserve cancellation by re-raising `asyncio.CancelledError` where broad exception handling is necessary.
- **Docstrings:** Google style (`Args:` / `Returns:` / `Raises:`). Comment non-obvious logic. Write all new comments in English. (Note: much existing code has Chinese comments; match the surrounding file when editing, but prefer English for new code.)
- **Version sync:** keep `[project].version` in `pyproject.toml` and `__version__` in `astrbot/__init__.py` in sync. `VERSION` in `astrbot/core/config/default.py` derives from `astrbot.__version__` — don't hardcode it.
- **Upstream sync:** the default sync method is **cherry-pick**, not merge. When syncing from `AstrBotDevs/AstrBot`, `git log <last_synced.commit>..upstream/master` to list the new commits, then cherry-pick each one in order. You may skip the upstream version-bump commit itself, but you must still carry the upstream release metadata in the same sync series: update `pyproject.toml`, `astrbot/__init__.py`, and the matching `changelogs/vX.Y.Z.md` once the fork has absorbed the commits for that upstream release. Adapt the changelog to match the commits actually absorbed into this fork: remove entries for skipped commits, keep entries for absorbed ones, and mention fork-specific deviations when needed. Resolve conflicts in favor of the fork's no-legacy, Python 3.14-only policy: never reintroduce 3.10–3.13 fallbacks or `AstrBotDevs`/`soulter` URLs, and preserve fork-specific docs (`uv`/`corepack pnpm` commands, the "modernized fork" declaration). Reserve `merge` for large bulk syncs where cherry-picking every commit is impractical.
- **Upstream sync marker:** after syncing, update `upstream-sync.yaml` at the repository root in the same change set. Record the upstream repo, branch, full commit hash, UTC sync time, sync method (`cherry-pick` or `merge`), and source PR or note. Use the full object name instead of an abbreviated hash so the recorded sync point stays unambiguous as the repository grows. Do not treat `.git/FETCH_HEAD` or `git notes` as the shared source of truth for upstream sync state.
- **No report files.** Don't create `*_SUMMARY.md` or similar artifacts.
- **Commits & PRs:** conventional commit format (`feat:`, `fix:`, `refactor:`, `chore:`), in English. Title under ~70 chars.

## Releases

Run release preparation from a clean worktree on `master`; the script fast-forwards the base branch, creates the short-lived `release/*` branch, bumps both version files, and writes the changelog:

```bash
uv run python scripts/prepare_release.py 4.26.0    # creates release/4.26.0 and runs checks
# flags: --generate-api-client  --dashboard-build  --commit --push
```

Open a PR from `release/x.y.z` to `master`. After merge, tag from the updated `master` (`git tag vx.y.z && git push origin vx.y.z`). Keep release branches only for maintained lines; delete one-off RC branches after tagging.
