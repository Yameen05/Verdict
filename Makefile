.PHONY: help dev up down build logs test backend-test backend-install frontend-install pinecone-init fetch-sample clean

help:
	@echo "Verdict dev targets:"
	@echo "  make dev               - docker-compose up (build if needed)"
	@echo "  make up                - docker-compose up -d"
	@echo "  make down              - docker-compose down"
	@echo "  make build             - rebuild images"
	@echo "  make logs              - tail logs"
	@echo "  make test              - run all tests"
	@echo "  make backend-test      - pytest in backend"
	@echo "  make backend-install   - pip install -r backend/requirements.txt (host venv)"
	@echo "  make frontend-install  - npm install in frontend"
	@echo "  make pinecone-init     - create the Pinecone index if it does not exist"
	@echo "  make fetch-sample TICKER=AAPL - fetch a 10-K and print head"
	@echo "  make clean             - remove caches and build artifacts"

dev:
	docker-compose up --build

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f --tail=100

test: backend-test

backend-test:
	cd backend && python -m pytest -v

backend-install:
	cd backend && python -m pip install -r requirements.txt

frontend-install:
	cd frontend && npm install

pinecone-init:
	cd backend && python -m app.scripts.pinecone_init

fetch-sample:
	cd backend && python -m app.scripts.fetch_sample $(TICKER)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.ruff_cache frontend/dist frontend/.vite
