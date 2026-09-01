# Tareas comunes. En Windows PowerShell usa ./tasks.ps1 (mismos targets).

PYTHON ?= python

.PHONY: install test lint format format-check ci hooks docker-up

install:
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) -m playwright install chromium 2>/dev/null || true

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m ruff check src tests --fix
	$(PYTHON) -m black src tests

format-check:
	$(PYTHON) -m black --check src tests

ci: lint format-check test

hooks:
	$(PYTHON) -m pre_commit install

docker-up:
	@test -f .env || (echo "== Crea .env desde .env.example primero ==" && exit 1)
	docker compose -f docker/docker-compose.yml up --build