# ENSO Shield - Master Makefile
# Standardized management across platforms (Windows, Linux, macOS)

ifeq ($(OS),Windows_NT)
    VENV_PY = services/api/.venv/Scripts/python.exe
    SYSTEM_PY ?= python
else
    VENV_PY = services/api/.venv/bin/python
    SYSTEM_PY ?= $(shell which python3 2>/dev/null || which python 2>/dev/null || echo python3)
endif

ifneq ($(wildcard $(VENV_PY)),)
    PYTHON ?= $(VENV_PY)
else
    PYTHON ?= $(SYSTEM_PY)
endif
DEVCTL = infrastructure/local/devctl.py
SVC ?= all
LINES ?= 100
FOLLOW ?= 0
TIMEOUT ?= 45
USE_FIXTURES ?= 0

.DEFAULT_GOAL := help
.PHONY: help env install run dev debug start stop restart status logs health \
        up up-build down docker-status docker-logs docker-health \
        ingest features train predict experiment-compare check test lint format typecheck build clean clean-all

##@ Help
help: ## Display this help message
	@$(PYTHON) $(DEVCTL) make-help $(firstword $(MAKEFILE_LIST))

##@ Local Development (Foreground Mode)
run: ## Run services in foreground (keeps terminal, Ctrl+C stops all) [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) run $(SVC)

dev: run ## Alias for 'run'

debug: ## Run services in foreground with DEBUG logging and hot-reload [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) run $(SVC) --debug

##@ Background Service Management (Detached Mode)
start: ## Start services in the background [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) start $(SVC) --timeout $(TIMEOUT)

stop: ## Stop background services [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) stop $(SVC)

restart: ## Restart background services [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) restart $(SVC)

status: ## Show running status, PIDs, URLs and health of background services
	@$(PYTHON) $(DEVCTL) status

logs: ## View background logs (use FOLLOW=1 to tail, LINES=N to adjust count)
	@$(PYTHON) $(DEVCTL) logs $(SVC) -n $(LINES) $(if $(filter 1 true,$(FOLLOW)),-f,)

health: ## Check HTTP health of running local services
	@$(PYTHON) $(DEVCTL) health --target local

##@ Docker Stack (Containerized)
up: ## Start the containerized stack in the background
	docker compose up -d

up-build: ## Rebuild images and start containerized stack in the background
	docker compose up -d --build

down: ## Stop the containerized stack
	docker compose down

docker-status: ## Show status of containerized services
	docker compose ps

docker-logs: ## Follow logs from containerized services
	docker compose logs -f

docker-health: ## Verify HTTP health of containerized services
	@$(PYTHON) $(DEVCTL) health --target docker

##@ Setup & Environment
install: ## Install dependencies for API and Web [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) install $(SVC)

env: ## Create .env from .env.example if missing
	@$(PYTHON) -c "import shutil, pathlib; p = pathlib.Path('.env'); p.is_file() or shutil.copy('.env.example', p); print('.env is ready')"

##@ Climate Data Pipeline
ingest: ## Ingest and validate climate data (raw -> cleaned -> derived) [USE_FIXTURES=1]
	@$(PYTHON) -m ml.data.cli ingest $(if $(filter 1 true True yes YES,$(USE_FIXTURES)),--use-fixtures,)

features: ## Extract zero-lookahead features and label drought targets [USE_FIXTURES=1]
	@$(PYTHON) -m ml.features.cli generate $(if $(filter 1 true True yes YES,$(USE_FIXTURES)),--use-fixtures,)

train: ## Train baseline and logistic regression experiment [USE_FIXTURES=1]
	@$(PYTHON) -m ml.training.cli train $(if $(filter 1 true True yes YES,$(USE_FIXTURES)),--use-fixtures,)

predict: ## Run probabilistic climate risk inference on sample input
	@$(PYTHON) -m ml.inference.cli predict --sample

experiment-compare: ## Compare Climatology, Logistic Regression, and XGBoost [USE_FIXTURES=1]
	@$(PYTHON) -m ml.experiments.cli compare $(if $(filter 1 true True yes YES,$(USE_FIXTURES)),--use-fixtures,)

##@ Quality & Testing
check: ## Run all static checks and tests (lint, typecheck, test) [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) check $(SVC)

test: ## Run automated tests [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) test $(SVC)

lint: ## Run linters (ruff, eslint) [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) lint $(SVC)

format: ## Format code (ruff format) [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) format $(SVC)

typecheck: ## Run static type checks (mypy, tsc) [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) typecheck $(SVC)

build: ## Build production assets [SVC=all|api|web]
	@$(PYTHON) $(DEVCTL) build $(SVC)

##@ Maintenance & Cleanup
clean: ## Remove temporary caches, logs, and build artifacts
	@$(PYTHON) $(DEVCTL) clean

clean-all: ## Remove caches, build artifacts, venv, and node_modules
	@$(PYTHON) $(DEVCTL) clean --all
