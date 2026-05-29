.PHONY: install lint typecheck test test-cov build clean

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy chcopy

test:
	uv run pytest --tb=short

test-cov:
	uv run pytest --tb=short --cov=chcopy --cov-report=term-missing

build:
	uv build

clean:
	rm -rf dist/ .venv/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
