# ENSO Shield - API Service Makefile

PYTHON ?= python
VENV_PYTHON = $(if $(filter Windows_NT,$(OS)),.venv/Scripts/python.exe,.venv/bin/python)

.PHONY: help install dev debug test lint format typecheck check clean

help:
	@echo API Service Commands:
	@echo   make install    - create virtualenv and install dependencies
	@echo   make dev        - run development server with hot reload
	@echo   make debug      - run development server with DEBUG logging
	@echo   make test       - run unit tests via pytest
	@echo   make lint       - check code style via ruff
	@echo   make format     - format code via ruff
	@echo   make typecheck  - check types via mypy
	@echo   make check      - run lint, typecheck, and test
	@echo   make clean      - clean python caches

install:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"

dev:
	$(VENV_PYTHON) -m uvicorn enso_api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src

debug:
	$(VENV_PYTHON) -m uvicorn enso_api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src --log-level debug

test:
	$(VENV_PYTHON) -m pytest

lint:
	$(VENV_PYTHON) -m ruff check .

format:
	$(VENV_PYTHON) -m ruff format .

typecheck:
	$(VENV_PYTHON) -m mypy

check: lint typecheck test

clean:
	@$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.mypy_cache'), pathlib.Path('.ruff_cache')]]; print('API caches cleaned')"
