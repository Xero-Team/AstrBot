.PHONY: worktree worktree-add worktree-rm pr-test-neo pr-test-full pr-test-full-fast \
	build build-all build-backend build-dashboard run run-backend run-dashboard \
	stop stop-backend stop-dashboard clean status docs napcat-schema-ob11-event napcat-schema-ob11-event-normalized napcat-models-ob11-event napcat-models-ob11-event-src napcat-codegen napcat-test napcat-check quality quality-report \
	quality-all quality-sync quality-pyright quality-bandit quality-audit quality-radon-cc quality-radon-mi \
	quality-report-all quality-report-pyright quality-report-bandit quality-report-audit quality-report-radon-cc quality-report-radon-mi \
	check check-all format format-all \
	check-py check-py-all check-py-format check-py-lint \
	check-web check-web-all check-web-build check-web-eslint check-web-smoke check-web-prettier \
	check-data check-md check-md-all check-md-prettier check-md-markdownlint check-toml check-toml-all check-toml-format check-toml-lint check-yaml check-yaml-all check-yaml-prettier check-yaml-lint \
	check-shell check-shell-all check-shell-shfmt check-shell-shellcheck check-ps check-docker \
	format-py format-web format-data format-md format-toml format-yaml format-shell format-ps

WORKTREE_DIR ?= ../astrbot_worktree
BRANCH ?= $(word 2,$(MAKECMDGOALS))
BASE ?= $(word 3,$(MAKECMDGOALS))
BASE ?= master

RUN_DIR ?= .make
DASHBOARD_DIR ?= dashboard
DOCS_DIR ?= docs
NAPCAT_SCHEMA_OUTPUT_DIR ?= .tmp/napcat-schema
NAPCAT_NORMALIZED_SCHEMA_PATH ?= $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11-all-event.normalized.schema.json
NAPCAT_MODELS_OUTPUT_PATH ?= $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11_event_models.py
NAPCAT_MODELS_SOURCE_PATH ?= astrbot/core/platform/sources/napcat/generated/ob11_events.py
PS := powershell -NoProfile -ExecutionPolicy Bypass -File
PNPM := corepack pnpm
NPX := npm exec --yes --
QUALITY_TYPE_TARGETS := astrbot/api astrbot/cli astrbot/core/backup astrbot/core/config astrbot/core/knowledge_base astrbot/core/skills astrbot/utils
QUALITY_SECURITY_TARGETS := astrbot/api astrbot/cli astrbot/core/backup astrbot/core/knowledge_base astrbot/core/skills astrbot/utils
CHECK_TARGETS := check-py check-web check-data check-md check-toml check-yaml check-shell check-ps check-docker
FORMAT_TARGETS := format-py format-web format-data format-md format-toml format-yaml format-shell format-ps
QUALITY_TARGETS := quality-pyright quality-bandit quality-audit quality-radon-cc quality-radon-mi
QUALITY_REPORT_TARGETS := quality-report-pyright quality-report-bandit quality-report-audit quality-report-radon-cc quality-report-radon-mi
CHECK_PY_TARGETS := check-py-format check-py-lint
CHECK_WEB_TARGETS := check-web-build check-web-eslint check-web-smoke check-web-prettier
CHECK_MD_TARGETS := check-md-prettier check-md-markdownlint
CHECK_TOML_TARGETS := check-toml-format check-toml-lint
CHECK_YAML_TARGETS := check-yaml-prettier check-yaml-lint
CHECK_SHELL_TARGETS := check-shell-shfmt check-shell-shellcheck
PARALLEL_JOBS ?= $(if $(NUMBER_OF_PROCESSORS),$(NUMBER_OF_PROCESSORS),4)
HAS_JOBSERVER := $(findstring --jobserver-auth=,$(MAKEFLAGS))
HAS_JOBS_FLAG := $(findstring -j,$(MAKEFLAGS))
PARALLEL_SUBMAKE_FLAGS := $(if $(strip $(HAS_JOBSERVER) $(HAS_JOBS_FLAG)),,-j$(PARALLEL_JOBS)) --output-sync=target --no-print-directory

worktree:
	@echo "Usage:"
	@echo "  make worktree-add <branch> [base-branch]"
	@echo "  make worktree-rm  <branch>"

worktree-add:
ifeq ($(strip $(BRANCH)),)
	$(error Branch name required. Usage: make worktree-add <branch> [base-branch])
endif
	@mkdir -p $(WORKTREE_DIR)
	git worktree add $(WORKTREE_DIR)/$(BRANCH) -b $(BRANCH) $(BASE)

worktree-rm:
ifeq ($(strip $(BRANCH)),)
	$(error Branch name required. Usage: make worktree-rm <branch>)
endif
	@if [ -d "$(WORKTREE_DIR)/$(BRANCH)" ]; then \
		git worktree remove $(WORKTREE_DIR)/$(BRANCH); \
	else \
		echo "Worktree $(WORKTREE_DIR)/$(BRANCH) not found."; \
	fi

pr-test-neo:
	@$(PS) scripts/pr_test_env.ps1 -Profile neo

pr-test-full:
	@$(PS) scripts/pr_test_env.ps1 -Profile full

pr-test-full-fast:
	@$(PS) scripts/pr_test_env.ps1 -Profile full -SkipSync -NoDashboard

build: build-all

build-all: build-backend build-dashboard

build-backend:
	uv sync

build-dashboard:
	cd $(DASHBOARD_DIR) && CI=true $(PNPM) install --no-frozen-lockfile
	cd $(DASHBOARD_DIR) && $(PNPM) build
	uv run python scripts/sync_dashboard_dist.py

run: build
	@$(MAKE) --no-print-directory run-backend
	@$(MAKE) --no-print-directory run-dashboard
	@$(MAKE) --no-print-directory status

run-backend:
	@$(PS) scripts/make_dev.ps1 run-backend

run-dashboard:
	@$(PS) scripts/make_dev.ps1 run-dashboard

stop: stop-dashboard stop-backend

stop-backend:
	@$(PS) scripts/make_dev.ps1 stop-backend

stop-dashboard:
	@$(PS) scripts/make_dev.ps1 stop-dashboard

status:
	@$(PS) scripts/make_dev.ps1 status

clean: stop
	@$(PS) scripts/make_dev.ps1 clean

docs:
	cd $(DOCS_DIR) && $(PNPM) install
	cd $(DOCS_DIR) && $(PNPM) run docs:dev

napcat-schema-ob11-event:
	@$(PS) scripts/napcat/generate_ob11_event_schema.ps1 -OutputDir $(NAPCAT_SCHEMA_OUTPUT_DIR)

napcat-schema-ob11-event-normalized: napcat-schema-ob11-event
	@$(PS) scripts/napcat/normalize_ob11_event_schema.ps1 \
		-SchemaPath $(NAPCAT_SCHEMA_OUTPUT_DIR)/ob11-all-event.schema.json \
		-OutputPath $(NAPCAT_NORMALIZED_SCHEMA_PATH)

napcat-models-ob11-event: napcat-schema-ob11-event-normalized
	@$(PS) scripts/napcat/generate_ob11_event_models.ps1 \
		-SchemaPath $(NAPCAT_NORMALIZED_SCHEMA_PATH) \
		-OutputPath $(NAPCAT_MODELS_OUTPUT_PATH)

napcat-models-ob11-event-src: napcat-schema-ob11-event-normalized
	@$(PS) scripts/napcat/generate_ob11_event_models.ps1 \
		-SchemaPath $(NAPCAT_NORMALIZED_SCHEMA_PATH) \
		-OutputPath $(NAPCAT_MODELS_SOURCE_PATH)

napcat-codegen: napcat-models-ob11-event-src

napcat-test:
	uv run pytest \
		tests/unit/test_napcat_adapter.py \
		tests/unit/test_napcat_codegen_scripts.py \
		tests/unit/test_napcat_codegen_powershell.py

napcat-check: napcat-codegen napcat-test

quality:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) quality-all

quality-all: $(QUALITY_TARGETS)
	@echo "==> focused quality checks passed"

quality-sync:
	uv sync --group dev

quality-pyright: quality-sync
	uv run pyright --project pyrightconfig.quality.json

quality-bandit: quality-sync
	PYTHONIOENCODING=utf-8 uv run bandit -r $(QUALITY_SECURITY_TARGETS) -c pyproject.toml

quality-audit: quality-sync
	uv run pip-audit

quality-radon-cc: quality-sync
	uv run radon cc $(QUALITY_TYPE_TARGETS) -s -n C

quality-radon-mi: quality-sync
	uv run radon mi $(QUALITY_TYPE_TARGETS) -s

quality-report:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) quality-report-all

quality-report-all: $(QUALITY_REPORT_TARGETS)
	@echo "==> full quality report generated"

quality-report-pyright: quality-sync
	uv run pyright

quality-report-bandit: quality-sync
	PYTHONIOENCODING=utf-8 uv run bandit -lll -iii -r astrbot -c pyproject.toml

quality-report-audit: quality-sync
	uv run pip-audit

quality-report-radon-cc: quality-sync
	uv run radon cc astrbot -s -n C

quality-report-radon-mi: quality-sync
	uv run radon mi astrbot -s

# Swallow extra args (branch/base) so make doesn't treat them as targets
%:
	@true

# ---------------------------------------------------------------------------
# Repo-wide formatting & linting
#
#   make check    verify every file type (CI-equivalent, no writes)
#   make format   auto-fix every file type
#
# Node tools (prettier, markdownlint-cli2, taplo) come from the root
# package.json; install once with `npm install`. yamllint comes from the uv
# dev group (`uv sync --group dev`). Shell/Dockerfile linters are native
# binaries: run if present, skipped with a notice otherwise (CI installs them).
# ---------------------------------------------------------------------------

check:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-all

check-all: $(CHECK_TARGETS)
	@echo "==> all checks passed"

format:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) format-all

format-all: $(FORMAT_TARGETS)
	@echo "==> formatting complete; run 'make check' to verify"

check-py:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-py-all

check-py-all: $(CHECK_PY_TARGETS)

check-py-format:
	@echo "==> [py] ruff format --check"
	uv run ruff format --check .

check-py-lint:
	@echo "==> [py] ruff check"
	uv run ruff check .

format-py:
	@echo "==> [py] ruff format + ruff check --fix"
	uv run ruff format .
	uv run ruff check --fix .

check-web:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-web-all

check-web-all: $(CHECK_WEB_TARGETS)

check-web-build:
	@echo "==> [web] build"
	cd $(DASHBOARD_DIR) && $(PNPM) build

check-web-eslint:
	@echo "==> [web] eslint"
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --concurrency=auto --max-warnings=0

check-web-smoke:
	@echo "==> [web] smoke tests"
	cd $(DASHBOARD_DIR) && $(PNPM) run test:smoke

check-web-prettier:
	@echo "==> [web] prettier --check"
	$(NPX) prettier --check "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"

format-web:
	@echo "==> [web] prettier + eslint --fix"
	$(NPX) prettier --write "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --concurrency=auto --fix

check-data:
	@echo "==> [data] prettier --check json/html"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.json','*.jsonc','*.html' \
		-ToolArgs '--check;--log-level;warn'

format-data:
	@echo "==> [data] prettier --write json/html"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.json','*.jsonc','*.html' \
		-ToolArgs '--write;--log-level;warn'

check-md:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-md-all

check-md-all: $(CHECK_MD_TARGETS)

check-md-prettier:
	@echo "==> [md] prettier --check"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.md' \
		-ToolArgs '--check;--log-level;warn'

check-md-markdownlint:
	@echo "==> [md] markdownlint-cli2"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool markdownlint-cli2 \
		-Patterns '*.md' \
		-ToolArgs '--no-globs'

format-md:
	@echo "==> [md] prettier --write + markdownlint-cli2 --fix"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.md' \
		-ToolArgs '--write;--log-level;warn'
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool markdownlint-cli2 \
		-Patterns '*.md' \
		-ToolArgs '--fix;--no-globs'

check-toml:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-toml-all

check-toml-all: $(CHECK_TOML_TARGETS)

check-toml-format:
	@echo "==> [toml] taplo fmt --check"
	@for f in $$(git ls-files '*.toml'); do \
		$(NPX) @taplo/cli fmt --check --stdin-filepath "$$f" - < "$$f" || exit 1; \
	done

check-toml-lint:
	@echo "==> [toml] taplo lint"
	@for f in $$(git ls-files '*.toml'); do \
		$(NPX) @taplo/cli lint - < "$$f" || exit 1; \
	done

format-toml:
	@echo "==> [toml] taplo fmt"
	@for f in $$(git ls-files '*.toml'); do \
		tmp=$$(mktemp); \
		$(NPX) @taplo/cli fmt --stdin-filepath "$$f" - < "$$f" > "$$tmp" && mv "$$tmp" "$$f"; \
	done

check-yaml:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-yaml-all

check-yaml-all: $(CHECK_YAML_TARGETS)

check-yaml-prettier:
	@echo "==> [yaml] prettier --check"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.yml','*.yaml' \
		-ToolArgs '--check;--log-level;warn'

check-yaml-lint:
	@echo "==> [yaml] yamllint"
	uv run yamllint --strict .

format-yaml:
	@echo "==> [yaml] prettier --write"
	@$(PS) scripts/run_tracked_node_tool.ps1 -Tool prettier \
		-Patterns '*.yml','*.yaml' \
		-ToolArgs '--write;--log-level;warn'

check-shell:
	@$(MAKE) $(PARALLEL_SUBMAKE_FLAGS) check-shell-all

check-shell-all: $(CHECK_SHELL_TARGETS)

check-shell-shfmt:
	@if command -v shfmt >/dev/null 2>&1; then \
		echo "==> [shell] shfmt -d"; \
		shfmt -d -i 2 -ci $$(git ls-files '*.sh'); \
	else echo "==> [shell] shfmt not found, skipping (CI enforces)"; fi

check-shell-shellcheck:
	@if command -v shellcheck >/dev/null 2>&1; then \
		echo "==> [shell] shellcheck"; \
		shellcheck -S style $$(git ls-files '*.sh'); \
	else echo "==> [shell] shellcheck not found, skipping (CI enforces)"; fi

format-shell:
	@if command -v shfmt >/dev/null 2>&1; then \
		echo "==> [shell] shfmt -w"; \
		shfmt -w -i 2 -ci $$(git ls-files '*.sh'); \
	else echo "==> [shell] shfmt not found, skipping"; fi

check-ps:
	@echo "==> [ps] PSScriptAnalyzer"
	@$(PS) scripts/lint_powershell.ps1

format-ps:
	@echo "==> [ps] Invoke-Formatter"
	@$(PS) scripts/lint_powershell.ps1 -Fix

check-docker:
	@if command -v hadolint >/dev/null 2>&1; then \
		echo "==> [docker] hadolint"; \
		hadolint --config .hadolint.yaml Dockerfile; \
	elif command -v docker >/dev/null 2>&1; then \
		if docker info >/dev/null 2>&1; then \
			echo "==> [docker] hadolint (via docker)"; \
			MSYS_NO_PATHCONV=1 docker run --rm -i -v "$$(pwd)/.hadolint.yaml:/config.yaml" hadolint/hadolint hadolint --config //config.yaml - < Dockerfile; \
		else echo "==> [docker] docker daemon unavailable, skipping (CI enforces)"; fi; \
	else echo "==> [docker] hadolint/docker not found, skipping (CI enforces)"; fi
