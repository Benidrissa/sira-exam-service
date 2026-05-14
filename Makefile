.PHONY: up down migrate shell-be shell-fe lint test

up:
	docker compose up --build

down:
	docker compose down

# Run Alembic migrations inside the backend container
migrate:
	docker compose run --rm backend alembic upgrade head

# Drop into a backend Python shell
shell-be:
	docker compose run --rm backend python

# Lint backend
lint-be:
	docker compose run --rm backend ruff check app migrations

# Lint frontend
lint-fe:
	docker compose run --rm frontend npm run lint

# Run backend tests
test-be:
	docker compose run --rm backend pytest

# Generate a new Alembic migration (pass MSG="description")
migration:
	docker compose run --rm backend alembic revision --autogenerate -m "$(MSG)"
