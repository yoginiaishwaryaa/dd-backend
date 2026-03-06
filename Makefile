help:
	@echo "Available commands:"
	@echo "  setup         Create venv, install deps, start docker, run migrations"
	@echo "  install       Install dependencies"
	@echo "  run           Run the production server"
	@echo "  dev           Run the development server with reload"
	@echo "  docker-up     Start the docker containers"
	@echo "  docker-down   Stop the docker containers"
	@echo "  migrate       Generate a new migration (usage: make migrate msg=\"message\")"
	@echo "  up            Apply all migrations"
	@echo "  up-one        Apply one migration step"
	@echo "  down          Downgrade to base"
	@echo "  down-one      Downgrade one migration step"
	@echo "  history       Show migration history"
	@echo "  clean         Remove cache files"
	@echo "  lint          Run ruff check and pyrefly check"
	@echo "  format        Run ruff format"

VENV := .venv
BIN := $(VENV)/bin
 
setup:
	python3 -m venv $(VENV)
	$(BIN)/pip install -r requirements.txt
	make docker-up
	sleep 3
	make up

install:
	$(BIN)/pip install -r requirements.txt
	
run:
	$(BIN)/uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	$(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	@if [ -z "$(msg)" ]; then echo "Error: Provide a message using msg=\"...\""; exit 1; fi
	$(BIN)/alembic revision --autogenerate -m "$(msg)"

up:
	$(BIN)/alembic upgrade head

up-one:
	$(BIN)/alembic upgrade +1

down:
	$(BIN)/alembic downgrade base

down-one:
	$(BIN)/alembic downgrade -1

history:
	$(BIN)/alembic history

clean:
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name ".coverage.*" -delete
	find . -type f -name ".coverage" -delete
	find . -type f -name "*.pyc" -delete
	rm -rf .ruff_cache

lint:
	-$(BIN)/ruff check
	-$(BIN)/pyrefly check

format:
	-$(BIN)/ruff format .
