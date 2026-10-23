# Every pipeline stage has one target. `make help` lists them.
# Optional parts (server/, web/, paper/, report/) are skipped with a message until they exist.

SHELL := /bin/bash
.DEFAULT_GOAL := help

UV       ?= uv
NPM      ?= npm
PORT_API ?= 8000
PORT_WEB ?= 5173
SUBJECTS ?= all

HAS_SERVER := $(wildcard server/pyproject.toml)
HAS_WEB    := $(wildcard web/package.json)
HAS_WEBLOCK:= $(wildcard web/package-lock.json)
HAS_PAPER  := $(wildcard paper/main.tex)
HAS_REPORT := $(wildcard report/Makefile)
HAS_BOOT   := $(wildcard _workspace/tools/bootstrap.sh)

.PHONY: help setup data verify-data audit epochs demo-bundle test test-real lint format check \
        server web demo e2e figures web-figures paper paper-supplement site-docs report doctor health clean

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Python env, git hooks, server and web dependencies
	@echo "==> Python environment (uv sync)"
	$(UV) sync
	@echo "==> git hooks (pre-commit)"
	$(UV) run pre-commit install
ifneq ($(HAS_BOOT),)
	@echo "==> workspace bootstrap"
	bash _workspace/tools/bootstrap.sh
else
	@echo "--- no _workspace/tools/bootstrap.sh, skipping workspace bootstrap"
endif
ifneq ($(HAS_SERVER),)
	@echo "==> server environment"
	$(UV) sync --project server
else
	@echo "--- no server/ yet, skipping"
endif
ifneq ($(HAS_WEBLOCK),)
	@echo "==> web dependencies (npm ci)"
	$(NPM) --prefix web ci
else ifneq ($(HAS_WEB),)
	@echo "==> web dependencies (npm install, no lockfile yet)"
	$(NPM) --prefix web install
else
	@echo "--- no web/ yet, skipping"
endif

health: ## Everything that must stay green: the CI gate, data integrity and the environment
	$(MAKE) check
	@if [ -d data/processed ]; then $(MAKE) verify-data; else echo "--- no data yet (make data)"; fi
	$(UV) run sixthfinger doctor

doctor: ## Versions, accelerator, disk space and data status
	$(UV) run sixthfinger doctor

data: ## Download processeddata.zip (3.5 GB), check md5, unzip, verify, delete the zip
	@echo "==> dataset download (resumable; rerun the same command if interrupted)"
	$(UV) run sixthfinger data download --archive processeddata

verify-data: ## Check extracted files against the saved listing
	$(UV) run sixthfinger data verify --archive processeddata

audit: ## Integrity audit of every run (phase P02)
	$(UV) run sixthfinger data audit

epochs: ## Cut and cache the 4 s windows (phase P03); SUBJECTS=sub-01,sub-03 for a subset
	$(UV) run sixthfinger epochs build --subjects $(SUBJECTS)

test: ## Unit tests on synthetic data (no download needed)
	$(UV) run pytest -q -m "not real_data"

demo-bundle: ## Export the demo model and rebuild web/public/demo (phase P10)
	$(UV) run sixthfinger export demo

test-real: ## Tests that need the downloaded dataset
	$(UV) run pytest -q -m real_data

lint: ## Ruff lint
	$(UV) run ruff check .

format: ## Apply ruff formatting
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

check: ## The CI gate: lint, format check, tests (and server/web checks when present)
	@echo "==> ruff"
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	@echo "==> pytest"
	$(UV) run pytest -q -m "not real_data"
ifneq ($(HAS_SERVER),)
	@echo "==> server tests"
	$(UV) run --project server pytest -q server/tests
endif
ifneq ($(HAS_WEB),)
	@echo "==> web lint, types, tests, build"
	$(NPM) --prefix web run lint
	$(NPM) --prefix web run typecheck
	$(NPM) --prefix web run test
	$(NPM) --prefix web run build
endif

server: ## Inference server on :$(PORT_API)
ifneq ($(HAS_SERVER),)
	cd server && $(UV) run uvicorn app.main:app --reload --port $(PORT_API)
else
	@echo "--- server/ does not exist yet (phase P10)"
endif

web: ## Demo frontend dev server on :$(PORT_WEB)
ifneq ($(HAS_WEB),)
	$(NPM) --prefix web run dev -- --port $(PORT_WEB)
else
	@echo "--- web/ does not exist yet (phase P11)"
endif

demo: ## Server and frontend together; Ctrl-C stops both
	@echo "==> API on http://localhost:$(PORT_API), demo on http://localhost:$(PORT_WEB)"
	$(MAKE) -j2 server web

e2e: ## Browser end-to-end tests of the demo (phase P12)
ifneq ($(HAS_WEB),)
	$(NPM) --prefix web run e2e
else
	@echo "--- web/ does not exist yet (phase P11)"
endif

figures: ## Compile the TikZ diagrams in paper/figures/tikz to PDF
	@command -v tectonic >/dev/null || { echo "Tectonic not installed: see phase P00"; exit 1; }
	cd paper/figures/tikz && for f in fig-*.tex; do tectonic -X compile $$f --outdir .. || exit 1; done

web-figures: ## Export the web page's figures to docs/figures/web and the paper's to paper/figures/web
ifneq ($(HAS_WEB),)
	$(NPM) --prefix web run figures
else
	@echo "--- web/ does not exist yet (phase P11)"
endif

paper: ## Build paper/main.pdf with Tectonic
ifneq ($(HAS_PAPER),)
	@command -v tectonic >/dev/null || { echo "Tectonic not installed: see phase P00"; exit 1; }
	mkdir -p paper/build
	tectonic -X compile paper/main.tex --outdir paper/build
else
	@echo "--- paper/main.tex does not exist yet (phase P13)"
endif

paper-supplement: ## Build the paper's reproducibility supplement (paper/build/supplement.pdf)
	@command -v tectonic >/dev/null || { echo "Tectonic not installed: see phase P00"; exit 1; }
	mkdir -p paper/build
	tectonic -X compile paper/supplement.tex --outdir paper/build

site-docs: paper ## Copy the paper, the slides and the report's public edition into web/public/docs
	$(MAKE) -C report public
	$(UV) run python scripts/copy_site_docs.py

report: ## Build the project report
ifneq ($(HAS_REPORT),)
	$(MAKE) -C report
else
	@echo "--- report/Makefile does not exist yet (phase P14)"
endif

clean: ## Remove caches and build products (never touches data/ or results/)
	rm -rf .pytest_cache .ruff_cache build dist paper/build report/build
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -exec rm -rf {} +
