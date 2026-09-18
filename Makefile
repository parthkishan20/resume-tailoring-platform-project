# ResumeTailor — one entry point for every quality gate.
#
# `make check` runs everything CI runs. CI runs these same targets, so local
# green means CI green (AGENTS.md section 8). Nothing here needs Docker, a
# network call to an LLM, or an API key.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV  ?= uv
NPM ?= npm

BACKEND  := backend
FRONTEND := frontend

# `uv run` from inside backend/ so pyproject.toml, uv.lock and .venv all resolve.
PY  := cd $(BACKEND) && $(UV) run --
FE  := $(NPM) --prefix $(FRONTEND) run

.PHONY: help install check secrets lint fmt fmt-check typecheck test \
        lint-backend lint-frontend fmt-backend fmt-frontend \
        typecheck-backend typecheck-frontend test-backend test-frontend \
        hooks dev build clean

## ---------------------------------------------------------------------------
## Everything
## ---------------------------------------------------------------------------

help:  ## Show this help
	@echo "ResumeTailor"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  make check is the gate. Run it before you report a task done."

install:  ## Install backend and frontend dependencies from the lockfiles
	cd $(BACKEND) && $(UV) sync --locked --all-groups
	cd $(FRONTEND) && $(NPM) ci

check: lint fmt-check typecheck test  ## Run every gate: lint, format, types, tests
	@echo ""
	@echo "  all gates passed"

secrets:  ## Scan tracked files and git history for secrets (gitleaks)
	@echo "==> gitleaks"
	@cd $(BACKEND) && $(UV) run -- pre-commit run gitleaks \
		--config ../.pre-commit-config.yaml --all-files --hook-stage pre-push
	@cd $(BACKEND) && $(UV) run -- pre-commit run gitleaks \
		--config ../.pre-commit-config.yaml --all-files
# `secrets` is deliberately NOT part of `check`. gitleaks only ever sees
# git-tracked files here, which is exactly what CI scans, but pre-commit has to
# fetch and build the hook environment on first use — and `check` must stay
# runnable offline. CI runs the scan on every push, and the pre-commit hook
# runs it on every commit, so nothing reaches a branch unscanned.

## ---------------------------------------------------------------------------
## Lint
## ---------------------------------------------------------------------------

lint: lint-backend lint-frontend  ## ruff check + eslint

lint-backend:
	@echo "==> ruff check"
	@$(PY) ruff check .

lint-frontend:
	@echo "==> eslint"
	@$(FE) lint

## ---------------------------------------------------------------------------
## Format
## ---------------------------------------------------------------------------

fmt: fmt-backend fmt-frontend  ## Rewrite files in place: ruff format + prettier

fmt-backend:
	@echo "==> ruff format"
	@$(PY) ruff format .
	@$(PY) ruff check --fix .

fmt-frontend:
	@echo "==> prettier --write"
	@$(FE) format

fmt-check:  ## Fail if anything is unformatted (this is what CI runs)
	@echo "==> ruff format --check"
	@$(PY) ruff format --check .
	@echo "==> prettier --check"
	@$(FE) format:check

## ---------------------------------------------------------------------------
## Types
## ---------------------------------------------------------------------------

typecheck: typecheck-backend typecheck-frontend  ## mypy + tsc --noEmit

typecheck-backend:
	@echo "==> mypy"
	@$(PY) mypy

typecheck-frontend:
	@echo "==> tsc --noEmit"
	@$(FE) typecheck

## ---------------------------------------------------------------------------
## Tests
## ---------------------------------------------------------------------------

test: test-backend test-frontend  ## pytest (with coverage floor) + jest

test-backend:
	@echo "==> pytest"
	@$(PY) pytest

test-frontend:
	@echo "==> jest"
	@$(FE) test

## ---------------------------------------------------------------------------
## Everything else
## ---------------------------------------------------------------------------

hooks:  ## Install the pre-commit, pre-push and commit-msg hooks
	@cd $(BACKEND) && $(UV) run -- pre-commit install \
		--config ../.pre-commit-config.yaml --install-hooks

dev:  ## Run the dev stack (backend on :8000, frontend on :3000)
	docker compose up --build

build:  ## Build the production image
	docker compose build

clean:  ## Remove caches and build output
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache
	rm -rf $(BACKEND)/.coverage $(BACKEND)/coverage.xml $(BACKEND)/htmlcov
	rm -rf $(FRONTEND)/.next $(FRONTEND)/out $(FRONTEND)/tsconfig.tsbuildinfo
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
