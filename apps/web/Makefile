# ENSO Shield - Web Frontend Makefile

NPM ?= npm

.PHONY: help install dev test lint typecheck build clean

help:
	@echo Web Frontend Commands:
	@echo   make install    - install npm dependencies
	@echo   make dev        - start Vite development server
	@echo   make test       - run tests via vitest
	@echo   make lint       - check code style via eslint
	@echo   make typecheck  - check types via tsc -b
	@echo   make build      - build production bundle
	@echo   make clean      - clean build artifacts and vite cache

install:
	$(NPM) install

dev:
	$(NPM) run dev

test:
	$(NPM) test

lint:
	$(NPM) run lint

typecheck:
	$(NPM) run typecheck

build:
	$(NPM) run build

clean:
	@node -e "const fs = require('fs'); ['dist', 'node_modules/.vite', 'node_modules/.tmp'].forEach(p => fs.rmSync(p, { recursive: true, force: true })); console.log('Web artifacts cleaned');"
