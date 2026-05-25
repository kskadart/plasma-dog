.PHONY: help install lint format typecheck tests run all clean

help:
	@echo "Доступные команды:"
	@echo "  make install    - установить зависимости через uv sync"
	@echo "  make lint       - запустить ruff проверку"
	@echo "  make format     - отформатировать код (black + ruff fix)"
	@echo "  make typecheck  - проверить типы через mypy"
	@echo "  make tests      - запустить pytest"
	@echo "  make run        - запустить приложение"
	@echo "  make all        - format + lint + typecheck + tests"
	@echo "  make clean      - удалить кэши и build артефакты"

install:
	uv sync

lint:
	uv run ruff check src/ tests/

format:
	uv run black src/ tests/
	uv run ruff check --fix src/ tests/

typecheck:
	uv run mypy src/

tests:
	uv run pytest tests/

run:
	uv run plasma-eye

all: format lint typecheck tests
	@echo "Все проверки пройдены."

clean:
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
