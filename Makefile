.PHONY: worktree worktree-add worktree-rm pr-test-neo pr-test-full pr-test-full-fast \
	build build-backend build-dashboard run run-backend run-dashboard \
	stop stop-backend stop-dashboard clean status quality quality-report \
	check format \
	check-py check-web check-data check-md check-toml check-yaml check-shell check-ps check-docker \
	format-py format-web format-data format-md format-toml format-shell format-ps

WORKTREE_DIR ?= ../astrbot_worktree
BRANCH ?= $(word 2,$(MAKECMDGOALS))
BASE ?= $(word 3,$(MAKECMDGOALS))
BASE ?= master

RUN_DIR ?= .make
DASHBOARD_DIR ?= dashboard
PS := powershell -NoProfile -ExecutionPolicy Bypass -File
PNPM := npm exec --yes pnpm@10 --
NPX := npm exec --yes --
QUALITY_TYPE_TARGETS := astrbot/api astrbot/cli astrbot/core/backup astrbot/core/config astrbot/core/knowledge_base astrbot/core/skills astrbot/utils
QUALITY_SECURITY_TARGETS := astrbot/api astrbot/cli astrbot/core/backup astrbot/core/knowledge_base astrbot/core/skills astrbot/utils

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
	./scripts/pr_test_env.sh --profile neo

pr-test-full:
	./scripts/pr_test_env.sh --profile full

pr-test-full-fast:
	./scripts/pr_test_env.sh --profile full --skip-sync --no-dashboard

build: build-backend build-dashboard

build-backend:
	uv sync

build-dashboard:
	cd $(DASHBOARD_DIR) && CI=true $(PNPM) install --no-frozen-lockfile
	cd $(DASHBOARD_DIR) && $(PNPM) build

run: build run-backend run-dashboard status

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

quality:
	uv sync --group dev
	uv run pyright --project pyrightconfig.quality.json
	PYTHONIOENCODING=utf-8 uv run bandit -r $(QUALITY_SECURITY_TARGETS) -c pyproject.toml
	uv run pip-audit
	uv run radon cc $(QUALITY_TYPE_TARGETS) -s -n C
	uv run radon mi $(QUALITY_TYPE_TARGETS) -s

quality-report:
	uv sync --group dev
	uv run pyright
	PYTHONIOENCODING=utf-8 uv run bandit -r astrbot -c pyproject.toml
	uv run pip-audit
	uv run radon cc astrbot -s -n C
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

check: check-py check-web check-data check-md check-toml check-yaml check-shell check-ps check-docker
	@echo "==> all checks passed"

format: format-py format-toml format-data format-md format-web format-shell format-ps
	@echo "==> formatting complete; run 'make check' to verify"

check-py:
	@echo "==> [py] ruff format --check + ruff check"
	uv run ruff format --check .
	uv run ruff check .

format-py:
	@echo "==> [py] ruff format + ruff check --fix"
	uv run ruff format .
	uv run ruff check --fix .

check-web:
	@echo "==> [web] typecheck + eslint + prettier"
	cd $(DASHBOARD_DIR) && $(PNPM) run typecheck
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --max-warnings=0
	$(NPX) prettier --check "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"

format-web:
	@echo "==> [web] prettier + eslint --fix"
	$(NPX) prettier --write "dashboard/src/**/*.{ts,mts,js,mjs,vue,scss,css}" "dashboard/*.{ts,mts,mjs}"
	cd $(DASHBOARD_DIR) && $(PNPM) exec eslint . --fix

check-data:
	@echo "==> [data] prettier --check json/css/scss/html"
	$(NPX) prettier --check "**/*.{json,jsonc,css,scss,html}"

format-data:
	@echo "==> [data] prettier --write json/css/scss/html"
	$(NPX) prettier --write "**/*.{json,jsonc,css,scss,html}"

check-md:
	@echo "==> [md] prettier --check + markdownlint-cli2"
	$(NPX) prettier --check "**/*.md"
	$(NPX) markdownlint-cli2 "**/*.md"

format-md:
	@echo "==> [md] prettier --write + markdownlint-cli2 --fix"
	$(NPX) prettier --write "**/*.md"
	$(NPX) markdownlint-cli2 --fix "**/*.md"

check-toml:
	@echo "==> [toml] taplo fmt --check + lint"
	@for f in $$(git ls-files '*.toml'); do \
		$(NPX) @taplo/cli fmt --check --stdin-filepath "$$f" - < "$$f" || exit 1; \
		$(NPX) @taplo/cli lint - < "$$f" || exit 1; \
	done

format-toml:
	@echo "==> [toml] taplo fmt"
	@for f in $$(git ls-files '*.toml'); do \
		tmp=$$(mktemp); \
		$(NPX) @taplo/cli fmt --stdin-filepath "$$f" - < "$$f" > "$$tmp" && mv "$$tmp" "$$f"; \
	done

check-yaml:
	@echo "==> [yaml] prettier --check + yamllint"
	$(NPX) prettier --check "**/*.{yml,yaml}"
	uv run yamllint --strict .

format-yaml:
	@echo "==> [yaml] prettier --write"
	$(NPX) prettier --write "**/*.{yml,yaml}"

check-shell:
	@if command -v shfmt >/dev/null 2>&1; then \
		echo "==> [shell] shfmt -d"; \
		shfmt -d -i 2 -ci $$(git ls-files '*.sh'); \
	else echo "==> [shell] shfmt not found, skipping (CI enforces)"; fi
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
		echo "==> [docker] hadolint (via docker)"; \
		MSYS_NO_PATHCONV=1 docker run --rm -i -v "$$(pwd)/.hadolint.yaml:/config.yaml" hadolint/hadolint hadolint --config //config.yaml - < Dockerfile; \
	else echo "==> [docker] hadolint/docker not found, skipping (CI enforces)"; fi
