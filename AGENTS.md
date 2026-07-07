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
uv sync                 # install deps (use --group dev for quality/test tooling)
uv run main.py          # run AstrBot; WebUI/API on http://localhost:6185
```

On first startup, AstrBot generates a random WebUI password, prints it in startup logs, and uses the default username `astrbot` until you change it. Runtime data (config, plugins, temp) lives under `data/`.

### Dashboard (Vue 3 + Vite, managed by `pnpm`)

```bash
cd dashboard
pnpm install            # first time only
pnpm dev                # http://localhost:3000
pnpm build              # production build into dashboard/dist/
pnpm generate:api       # regenerate the typed API client (see below)
```

### Tests

```bash
uv run pytest                                  # full suite
uv run pytest tests/unit                       # unit tests only
uv run pytest tests/unit/test_event_bus.py     # single file
uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_dispatch  # single test
uv run pytest --test-profile blocking          # exclude auto-classified tier_c/tier_d (slow/integration) tests
```

Tests use `pytest-asyncio`; async tests are marked explicitly with `@pytest.mark.asyncio`. `conftest.py` sets `TESTING=true` and `ASTRBOT_TEST_MODE=true`, reorders unit tests before integration tests, and auto-classifies slow/integration tests into `tier_c`/`tier_d`. Shared fixtures (`event_queue`, `temp_data_dir`, etc.) live in `tests/conftest.py` and `tests/fixtures/`.

### Lint, format, quality

```bash
ruff format .           # format (run before committing)
ruff check .            # lint
make quality            # scoped pyright + bandit + pip-audit + radon on key modules
make quality-report     # same checks across the whole astrbot package
```

`ruff` is configured in `pyproject.toml` (line-length 88, py314 target, mccabe max-complexity 15). Pre-commit hooks run `ruff-check`, `ruff-format`, and `pyupgrade --py314-plus`:

```bash
pip install pre-commit && pre-commit install
```

## Architecture

AstrBot routes incoming messages from many IM platforms through a staged pipeline that ultimately invokes an LLM agent and/or plugins, then sends a response back. The big pieces:

### Message flow

1. **Platform adapters** (`astrbot/core/platform/sources/*`) connect to each IM (QQ official, OneBot/aiocqhttp, Telegram, Discord, Lark, DingTalk, Slack, etc.). Each adapter normalizes inbound messages into an `AstrMessageEvent` (`astrbot/core/platform/astr_message_event.py`) and pushes it onto a shared asyncio queue.
2. **`EventBus`** (`astrbot/core/event_bus.py`) pulls events off the queue, looks up the right `PipelineScheduler` for the event's config (keyed by config id via `AstrBotConfigManager`), and spawns a task to run it.
3. **Pipeline** (`astrbot/core/pipeline/`) runs the event through ordered stages defined in `stage_order.py`:
   `WakingCheck → WhitelistCheck → SessionStatusCheck → RateLimit → ContentSafetyCheck → PreProcess → Process → ResultDecorate → Respond`.
   The **ProcessStage** is where plugins (Stars) and the LLM agent run; `ResultDecorate` applies reply prefixes, text-to-image, TTS; `Respond` sends the message back through the platform adapter.

### Agent & providers

- **`astrbot/core/agent/`** is the LLM agent runtime: tool execution (`tool_executor.py`), MCP client (`mcp_client.py`), handoffs, runners, and run context. The main agent assembly lives in `astrbot/core/astr_main_agent.py` and related `astr_agent_*` modules. `astrbot/core/subagent_orchestrator.py` manages sub-agents.
- **`astrbot/core/provider/`** abstracts LLM/STT/TTS/embedding/rerank services. Concrete integrations live in `provider/sources/*` (OpenAI, Anthropic, Gemini, Dify, etc.). `ProviderManager` (`provider/manager.py`) tracks instances and the default provider; `func_tool_manager.py` manages function tools exposed to the LLM.

### Plugins ("Stars")

- The plugin system is under `astrbot/core/star/`. Plugins are called **Stars**; `StarMetadata` (`star/star.py`) describes each one. Built-in plugins live in `astrbot/builtin_stars/`; user-installed plugins load from `data/plugins/`. `PluginManager` (`star_manager.py`) loads/registers them and `star_handler.py` wires their handlers and filters into the pipeline.

### Lifecycle & supporting subsystems

- **`AstrBotCoreLifecycle`** (`astrbot/core/core_lifecycle.py`) is the startup/shutdown orchestrator — it constructs the provider/platform/conversation/plugin managers, pipeline schedulers, event bus, cron manager, knowledge base, and persona manager, then runs all tasks.
- Other core subsystems: `knowledge_base/` (chunking + retrieval, FAISS/BM25), `conversation_mgr.py`, `persona_mgr.py`, `cron/` (APScheduler-based jobs), `skills/`, `computer/` (agent sandbox), `db/`, and `backup/`.

### Dashboard ↔ backend contract

- The backend API lives under `astrbot/dashboard/`. The OpenAPI definition is `openspec/openapi-v1.yaml`. The frontend (`dashboard/src/api/generated/`) is a **generated** typed client. **When you change backend routes, request/response schemas, or the OpenAPI spec, regenerate the client with `cd dashboard && pnpm generate:api`** and commit the result.

### CLI

The `astrbot` console entry point (`astrbot/cli/__main__.py`, commands in `astrbot/cli/commands/`) drives `astrbot init` / `astrbot run` for `uv tool` installs.

## Conventions

- **KISS / first principles.** Identify the real problem and the smallest correct change. Do not add features, config switches, abstractions, dependencies, or compatibility layers without clear, current need.
- **Inline-first, few helpers.** Implement logic inline within the main function. Only extract a helper when the exact logic repeats in 3+ places or inlining makes a function exceed ~50 lines. Do not split continuous linear logic into tiny functions. When editing existing code, don't restructure or extract helpers unless the code already violates these rules.
- **Cross-platform.** When relevant, consider behavior on Windows, macOS, and Linux, and on Arm64/x86 platforms, while keeping the current Python 3.14+ baseline.
- **Paths:** use `pathlib.Path`, not string paths. Get AstrBot data/temp directories via `astrbot.core.utils.astrbot_path` (e.g. `get_astrbot_data_path()`, `get_astrbot_temp_path()`) — don't hardcode.
- **Docstrings:** Google style (`Args:` / `Returns:` / `Raises:`). Comment non-obvious logic. Write all new comments in English. (Note: much existing code has Chinese comments; match the surrounding file when editing, but prefer English for new code.)
- **Version sync:** keep `[project].version` in `pyproject.toml` and `__version__` in `astrbot/__init__.py` in sync. `VERSION` in `astrbot/core/config/default.py` derives from `astrbot.__version__` — don't hardcode it.
- **Upstream sync:** the default sync method is **cherry-pick**, not merge. When syncing from `AstrBotDevs/AstrBot`, `git log <last_synced.commit>..upstream/master` to list the new commits, then cherry-pick each one in order. You may skip the upstream version-bump commit itself, but you must still carry the upstream release metadata in the same sync series: update `pyproject.toml`, `astrbot/__init__.py`, and the matching `changelogs/vX.Y.Z.md` once the fork has absorbed the commits for that upstream release. Adapt the changelog to match the commits actually absorbed into this fork: remove entries for skipped commits, keep entries for absorbed ones, and mention fork-specific deviations when needed. Resolve conflicts in favor of the fork's no-legacy, Python 3.14-only policy: never reintroduce 3.10–3.13 fallbacks or `AstrBotDevs`/`soulter` URLs, and preserve fork-specific docs (`uv`/`corepack pnpm` commands, the "modernized fork" declaration). Reserve `merge` for large bulk syncs where cherry-picking every commit is impractical.
- **Upstream sync marker:** after syncing, update `upstream-sync.yaml` at the repository root in the same change set. Record the upstream repo, branch, full commit hash, UTC sync time, sync method (`cherry-pick` or `merge`), and source PR or note. Use the full object name instead of an abbreviated hash so the recorded sync point stays unambiguous as the repository grows. Do not treat `.git/FETCH_HEAD` or `git notes` as the shared source of truth for upstream sync state.
- **No report files.** Don't create `*_SUMMARY.md` or similar artifacts.
- **Commits & PRs:** conventional commit format (`feat:`, `fix:`, `refactor:`, `chore:`), in English. Title under ~70 chars.

## Releases

Prepare releases from a clean worktree on a short-lived `release/*` branch:

```bash
uv run python scripts/prepare_release.py 4.26.0    # bumps version, writes changelog, runs checks
# flags: --generate-api-client  --dashboard-build  --commit --push
```

Open a PR from `release/x.y.z` to `master`. After merge, tag from the updated `master` (`git tag vx.y.z && git push origin vx.y.z`). Keep release branches only for maintained lines; delete one-off RC branches after tagging.
